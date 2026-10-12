"""Single-panel NTE launcher using the original DLL CBT hook protocol."""
from __future__ import annotations

import configparser
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import uuid

PLUGIN_NAME = re.compile(r"anticensor(?:\.asi)+", re.IGNORECASE)


def digest(file: Path) -> str:
    with file.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def redirected(path: Path) -> bool:
    metadata = path.lstat()
    return path.is_symlink() or bool(getattr(metadata, "st_file_attributes", 0) & 0x400)


def active_plugins(game_bin: Path) -> list[Path]:
    result = []
    for folder in (game_bin, game_bin / "plugins"):
        if not folder.exists():
            continue
        if redirected(folder):
            raise ValueError("拒绝修改重定向的游戏插件目录。")
        for file in folder.iterdir():
            if PLUGIN_NAME.fullmatch(file.name) and file.is_file():
                if redirected(file):
                    raise ValueError("拒绝修改符号链接形式的反虚化插件。")
                result.append(file)
    return result


def register_plugin(game_bin: Path, storage: Path) -> None:
    """Preserve the installed plugin externally without changing its active mode."""
    candidates = active_plugins(game_bin)
    if len(candidates) != 1:
        raise ValueError("需要找到且仅找到一个反虚化插件，不能猜测应当使用哪一份。")
    source = candidates[0]
    storage.mkdir(parents=True, exist_ok=True)
    if redirected(storage):
        raise ValueError("反虚化存储目录不能是符号链接。")
    stored = storage / source.name
    if stored.exists():
        if redirected(stored) or digest(stored) != digest(source):
            raise ValueError("外部反虚化插件与当前游戏文件不同，拒绝覆盖。")
    else:
        shutil.copy2(source, stored)
    metadata = {"filename": source.name, "game_relative_path": source.relative_to(game_bin).as_posix(), "sha256": digest(source)}
    (storage / "anticensor.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


class AnticensorController:
    def __init__(self, game_bin: Path, storage: Path):
        self.game_bin = game_bin.resolve(strict=True)
        self.storage = storage.resolve(strict=True)
        if self.storage == self.game_bin or self.storage.is_relative_to(self.game_bin):
            raise ValueError("反虚化可选插件必须保存在游戏目录之外。")
        metadata = json.loads((self.storage / "anticensor.json").read_text(encoding="utf-8"))
        filename = metadata["filename"]
        relative = Path(metadata["game_relative_path"])
        if not PLUGIN_NAME.fullmatch(filename) or relative.parts not in ((filename,), ("plugins", filename)):
            raise ValueError("反虚化插件配置包含无效路径。")
        self.source = self.storage / filename
        self.target = self.game_bin / relative
        self.expected_hash = metadata["sha256"]
        if redirected(self.source) or digest(self.source) != self.expected_hash:
            raise ValueError("外部反虚化插件缺失或校验不符。")

    def is_enabled(self) -> bool:
        return bool(active_plugins(self.game_bin))

    def set_enabled(self, enabled: bool) -> None:
        if digest(self.source) != self.expected_hash:
            raise ValueError("外部反虚化插件校验不符。")
        candidates = active_plugins(self.game_bin)
        if len(candidates) > 1:
            raise ValueError("发现多份反虚化插件；请先处理重复文件，避免重复加载。")
        if candidates:
            active = candidates[0]
            if active != self.target or digest(active) != self.expected_hash:
                raise ValueError("当前游戏中的反虚化插件发生变化，拒绝覆盖或移走未知文件。")
            if not enabled:
                # Move the only allowlisted optional plugin out of the game.
                # shutil.move handles the installed C: -> library F: case.
                staged = self.storage / (self.source.name + ".transfer-" + uuid.uuid4().hex)
                shutil.move(str(active), str(staged))
                os.replace(staged, self.source)
            return
        if not enabled:
            return
        self.target.parent.mkdir(parents=True, exist_ok=True)
        if redirected(self.target.parent):
            raise ValueError("目标插件目录不能是符号链接。")
        staged = self.target.with_name(self.target.name + ".transfer-" + uuid.uuid4().hex)
        shutil.copy2(self.source, staged)
        if digest(staged) != self.expected_hash:
            staged.unlink()
            raise ValueError("复制反虚化插件后校验失败。")
        os.replace(staged, self.target)


def game_binary_directory(loader_dir: Path) -> Path:
    config = configparser.ConfigParser()
    config.read(loader_dir / "config.ini", encoding="utf-8-sig")
    launcher = Path(config.get("Settings", "Launcher"))
    if not launcher.is_file():
        raise ValueError("请在原 Mod Loader 设置中配置正确的异环启动器。")
    target = launcher.parent / "Client/WindowsNoEditor/HT/Binaries/Win64"
    if not (target / "HTGame.exe").is_file():
        raise ValueError("没有找到异环 HTGame.exe，请检查启动器路径。")
    return target


def game_is_running() -> bool:
    if sys.platform != "win32":
        return False
    class ProcessEntry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", wintypes.WCHAR * 260)]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        more = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            if entry.szExeFile.lower() in ("htgame.exe", "htgame-win64-shipping.exe"):
                return True
            more = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        return False
    finally:
        kernel.CloseHandle(snapshot)


class NativeHook:
    """Keep the exported native hook and module alive until explicit release."""
    def __init__(self, dll: Path):
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel.LoadLibraryW.argtypes = [wintypes.LPCWSTR]
        self.kernel.LoadLibraryW.restype = wintypes.HMODULE
        self.kernel.GetProcAddress.argtypes = [wintypes.HMODULE, ctypes.c_char_p]
        self.kernel.GetProcAddress.restype = ctypes.c_void_p
        self.kernel.FreeLibrary.argtypes = [wintypes.HMODULE]
        self.user.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, wintypes.HMODULE, wintypes.DWORD]
        self.user.SetWindowsHookExW.restype = wintypes.HANDLE
        self.user.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
        self.module = self.kernel.LoadLibraryW(str(dll))
        self.hook = None
        if not self.module:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            callback = self.kernel.GetProcAddress(self.module, b"CBTProc")
            if not callback:
                raise ValueError("Mod Loader DLL 缺少 CBTProc 导出。")
            self.hook = self.user.SetWindowsHookExW(5, callback, self.module, 0)
            if not self.hook:
                raise ctypes.WinError(ctypes.get_last_error())
        except Exception:
            self.close()
            raise

    def close(self):
        if self.hook:
            if not self.user.UnhookWindowsHookEx(self.hook):
                raise ctypes.WinError(ctypes.get_last_error())
            self.hook = None
        if self.module:
            self.kernel.FreeLibrary(self.module)
            self.module = None


def launch_official(launcher: Path):
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    shell.ShellExecuteW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                   wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_int]
    shell.ShellExecuteW.restype = ctypes.c_void_p
    result = shell.ShellExecuteW(None, "open", str(launcher), None, str(launcher.parent), 1)
    if not result or result <= 32:
        raise OSError(f"启动异环官方启动器失败（{result}）。")


def start_game(root: Path, enabled: bool, controller: AnticensorController,
               hook_factory=NativeHook, launch=launch_official):
    if game_is_running():
        raise ValueError("请先退出异环，再选择是否开启反虚化。")
    loader_dir = root / "Mod Loader"
    dll = loader_dir / "MyCustomLoader.dll"
    bypass = loader_dir / "plugins/UniversalSigBypasser.asi"
    for file in (dll, bypass):
        if not file.is_file() or redirected(file):
            raise ValueError("Mod Loader 文件不完整或路径被重定向。")
    config = configparser.ConfigParser()
    config.read(loader_dir / "config.ini", encoding="utf-8-sig")
    launcher = Path(config.get("Settings", "Launcher"))
    if not launcher.is_file():
        raise ValueError("没有找到 config.ini 中的异环官方启动器。")
    if enabled and not (controller.game_bin / "cutils.dll").is_file():
        raise ValueError("游戏目录缺少反虚化插件需要的 cutils.dll。")
    # The original loader copies its plugins folder into the game executable folder.
    target_dir = controller.game_bin / "plugins"
    target_dir.mkdir(exist_ok=True)
    if redirected(target_dir):
        raise ValueError("目标插件目录不能是符号链接。")
    sources = [f for f in (loader_dir / "plugins").iterdir() if f.is_file()]
    for source in sources:
        target = target_dir / source.name
        if redirected(source) or (target.exists() and (redirected(target) or digest(target) != digest(source))):
            raise ValueError(f"插件 {source.name} 与游戏中的文件不同，拒绝覆盖。")
        if PLUGIN_NAME.fullmatch(source.name):
            raise ValueError("反虚化插件必须放在 Optional Plugins，不能放在通用插件目录。")
    for source in sources:
        target = target_dir / source.name
        if not target.exists():
            shutil.copy2(source, target)
    previous_mode = controller.is_enabled()
    controller.set_enabled(enabled)
    hook = None
    try:
        hook = hook_factory(dll)
        launch(launcher)
        return hook
    except Exception:
        if hook:
            hook.close()
        controller.set_enabled(previous_mode)
        raise


def installation_root(executable: Path) -> Path:
    parent = executable.resolve().parent
    return parent.parent if parent.name == "Mod Loader" else parent


def main() -> None:
    import tkinter as tk
    from tkinter import messagebox, ttk
    root_path = installation_root(Path(sys.executable)) if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    window = tk.Tk()
    window.title("异环 Mod 启动器")
    window.resizable(False, False)
    window.geometry("560x260")
    style = ttk.Style(window)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    style.configure("Launch.TButton", font=("Microsoft YaHei UI", 12), padding=(12, 15))
    panel = ttk.Frame(window, padding=24)
    panel.pack(fill="both", expand=True)
    ttk.Label(panel, text="选择反虚化启动方式", font=("Microsoft YaHei UI", 15)).pack(pady=(0, 10))
    status = tk.StringVar(value="选择后直接注入并启动异环官方启动器。")
    ttk.Label(panel, textvariable=status, font=("Microsoft YaHei UI", 10)).pack(pady=(0, 15))
    buttons = ttk.Frame(panel)
    buttons.pack(fill="x")
    buttons.columnconfigure((0, 1), weight=1)
    active_hook = None
    def release_hook():
        nonlocal active_hook
        if active_hook:
            active_hook.close()
            active_hook = None

    def await_game():
        if not active_hook:
            return
        if game_is_running():
            status.set("已检测到游戏，正在完成注入…")
            window.after(15000, finish_injection)
        else:
            window.after(1000, await_game)

    def finish_injection():
        release_hook()
        status.set("启动流程已完成，可关闭此窗口。")

    def close_window():
        release_hook()
        window.destroy()

    window.protocol("WM_DELETE_WINDOW", close_window)
    def choose(enabled: bool) -> None:
        nonlocal active_hook
        try:
            game_bin = game_binary_directory(root_path / "Mod Loader")
            controller = AnticensorController(game_bin, root_path / "Optional Plugins")
            if active_hook:
                return
            active_hook = start_game(root_path, enabled, controller)
        except Exception as error:
            messagebox.showerror("无法启动", str(error), parent=window)
            return
        for button in buttons.winfo_children():
            button.configure(state="disabled")
        status.set("已启动官方启动器；请启动游戏，等待注入完成。")
        window.after(1000, await_game)
    ttk.Button(buttons, text="开启反虚化启动", style="Launch.TButton", command=lambda: choose(True)).grid(row=0, column=0, sticky="ew", padx=(0, 8))
    ttk.Button(buttons, text="不开反虚化启动", style="Launch.TButton", command=lambda: choose(False)).grid(row=0, column=1, sticky="ew", padx=(8, 0))
    ttk.Label(panel, text="切换反虚化需要先退出游戏。", font=("Microsoft YaHei UI", 9)).pack(pady=(14, 0))
    window.update_idletasks()
    window.geometry(f"{max(560, window.winfo_reqwidth())}x{max(260, window.winfo_reqheight())}")
    window.mainloop()


if __name__ == "__main__":
    main()
