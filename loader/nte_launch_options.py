"""NTE launch choices around the existing, unchanged Mod Loader executable."""
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
import subprocess
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


def start_existing_loader(root: Path, enabled: bool, controller: AnticensorController) -> subprocess.Popen:
    if game_is_running():
        raise ValueError("请先退出异环，再选择是否开启反虚化。已加载的插件需要重启游戏才能切换。")
    loader_dir = root / "Mod Loader"
    executable = loader_dir / "Game start.exe"
    for file in (executable, loader_dir / "MyCustomLoader.dll", loader_dir / "plugins/UniversalSigBypasser.asi"):
        if not file.is_file():
            raise ValueError("原 Mod Loader 文件不完整，请恢复启动器文件。")
    if enabled and not (controller.game_bin / "cutils.dll").is_file():
        raise ValueError("游戏目录缺少反虚化插件需要的 cutils.dll。")
    previous_mode = controller.is_enabled()
    controller.set_enabled(enabled)
    try:
        flags = (subprocess.CREATE_NEW_CONSOLE | subprocess.HIGH_PRIORITY_CLASS) if sys.platform == "win32" else 0
        return subprocess.Popen([str(executable)], cwd=str(loader_dir), creationflags=flags)
    except Exception:
        controller.set_enabled(previous_mode)
        raise


def main() -> None:
    import tkinter as tk
    from tkinter import messagebox, ttk
    root_path = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    window = tk.Tk()
    window.title("异环 Mod 启动选项")
    window.resizable(False, False)
    window.geometry("560x260")
    style = ttk.Style(window)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    style.configure("Launch.TButton", font=("Microsoft YaHei UI", 12), padding=(12, 15))
    panel = ttk.Frame(window, padding=24)
    panel.pack(fill="both", expand=True)
    ttk.Label(panel, text="选择反虚化启动方式", font=("Microsoft YaHei UI", 15)).pack(pady=(0, 10))
    ttk.Label(panel, text="选择后进入原有 Mod Loader 启动流程。", font=("Microsoft YaHei UI", 10)).pack(pady=(0, 15))
    buttons = ttk.Frame(panel)
    buttons.pack(fill="x")
    buttons.columnconfigure((0, 1), weight=1)
    def choose(enabled: bool) -> None:
        try:
            game_bin = game_binary_directory(root_path / "Mod Loader")
            controller = AnticensorController(game_bin, root_path / "Optional Plugins")
            start_existing_loader(root_path, enabled, controller)
        except Exception as error:
            messagebox.showerror("无法启动", str(error), parent=window)
            return
        window.destroy()
    ttk.Button(buttons, text="开启反虚化启动", style="Launch.TButton", command=lambda: choose(True)).grid(row=0, column=0, sticky="ew", padx=(0, 8))
    ttk.Button(buttons, text="不开反虚化启动", style="Launch.TButton", command=lambda: choose(False)).grid(row=0, column=1, sticky="ew", padx=(8, 0))
    ttk.Label(panel, text="切换反虚化需要先退出游戏。", font=("Microsoft YaHei UI", 9)).pack(pady=(14, 0))
    window.update_idletasks()
    window.geometry(f"{max(560, window.winfo_reqwidth())}x{max(260, window.winfo_reqheight())}")
    window.mainloop()


if __name__ == "__main__":
    main()
