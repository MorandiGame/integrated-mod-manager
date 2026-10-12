# 异环现有 Mod Loader 静态分析

后续变更：外层 `Mod注入器.exe` 已增加“开启反虚化启动”和“不开反虚化启动”两个选择。
它先切换游戏目录中的 `Anticensor.asi.asi`，再打开原有 `Game start.exe` 启动面板。
原生 `Game start.exe`、`MyCustomLoader.dll`、`UniversalSigBypasser.asi` 没有改动。
外层实现与验证见 `loader/README.md`；下文保留原始包装的逆向证据。

分析日期：2026-10-12。读取原文件、提取 Python 字节码、分析 PE 导入/导出与 x64
反汇编；没有运行或修改 bypass。下列地址是本次文件的静态虚拟地址，版本变化后不能照搬。
这是调用链与关键逻辑的恢复，不等同于获得原作者的完整 C++ 工程。

## 调用链

```text
IMM 的启动按钮
  └─ Mod注入器.exe（PyInstaller / Python 3.13 的外层包装）
      ├─ 检查管理员权限，必要时使用 ShellExecuteW("runas") 重启自身
      ├─ 找到自身旁边的 Mod Loader 目录
      ├─ 将工作目录切换到 Mod Loader
      └─ subprocess.Popen("Game start.exe", 新控制台 | 高优先级)
          └─ Game start.exe（原生 x64 GUI）
              ├─ 读取 config.ini 的 Launcher、Target、DllName 等设置
              ├─ 加载 MyCustomLoader.dll，解析 CBTProc 导出
              ├─ SetWindowsHookExW(WH_CBT=5, CBTProc, DLL, threadId=0)
              └─ 游戏进程载入 MyCustomLoader.dll
                  ├─ DllMain 创建工作线程，延迟约 3000ms
                  ├─ 识别当前进程名称并查找 plugins 内的 .asi 文件
                  └─ LoadLibraryW(ASI 的完整路径)
                      └─ UniversalSigBypasser.asi
                          ├─ 获取当前 EXE 模块及其内存范围
                          ├─ 扫描若干候选字节特征
                          ├─ 修改匹配到的分支位置
                          └─ 恢复页保护、刷新指令缓存、写日志
```

## 逐层证据

外层包装可以从 PyInstaller CArchive 提取。包中带 `python313.dll`，用户脚本
字节码包含 `get_exe_dir`、`is_admin`、`run_as_admin` 和 `main`。恢复出的 `main`
明确将自身目录拼接为 `Mod Loader/Game start.exe`，使用 `os.chdir` 后再 `Popen`。
它没有直接执行 pak 加载、内存扫描或签名补丁；把 exe 与相邻目录整体迁移即可保留路径关系。

`Game start.exe` 在 `0x14004f4fe` 调用 `LoadLibraryExA`，在
`0x14004f51a` 解析 `CBTProc`，在 `0x14004f9b1` 调用
`SetWindowsHookExW`。调用前 `ecx=5`、`r9d=0`，说明是全局 CBT 钩子。
这条实际调用链使用 Windows 钩子让 DLL 随进程窗口事件进入目标进程；本次未发现
常见的 `OpenProcess → VirtualAllocEx → WriteProcessMemory → CreateRemoteThread`
调用链。程序还包含复制 `plugins` 的 `SHFileOperationA` 路径，不能把它视为
完全无文件副作用的注入器。

`MyCustomLoader.dll` 唯一导出是 `CBTProc`。`0x180005010` 的 DLL attach
分支禁用线程通知并创建线程，线程入口为 `0x180003c30`，入口先 `Sleep(3000)`。
它读取宿主 EXE 路径，进行进程名筛选（包含 `htgame`），构造 `\plugins` 路径并
判断 `.asi` 扩展；`0x1800045bd` 调用 `LoadLibraryW`。因此它是插件加载层，
并没有把 `UniversalSigBypasser.asi` 名称硬编码成唯一插件。

`UniversalSigBypasser.asi` 的 `0x1800012b0` 所在函数通过
`GetModuleHandleA`、`K32GetModuleInformation` 获取模块内存并进行特征匹配。
主处理函数遍历六组候选特征，命中后选取对应偏移。补丁函数调用
`VirtualProtect`（`0x18000188a`）、写入分支位置、
`FlushInstructionCache`（`0x180001a35`）并恢复保护（`0x180001a4b`）。
字符串包括 `Pattern not found!`、`Wrong jump instruction offset at:`、
`Patch applied at 0x` 和 `SigBypasser.log`。这些证据说明它在运行时改变校验相关
分支；这不是重新打包 pak，也不是让 IMM 直接成为 Unreal pak 加载器。

## 文件指纹

| 文件 | SHA-256 |
| --- | --- |
| Mod注入器.exe | `4b6bc988767d9f3d2c51d4f9bcd11a4602c78d922a129cf21602e4c83c200a34` |
| Game start.exe | `fb53deaf600d6bcfcd8927f3cbff9f1b31df77bc136d520f592637cb437facf4` |
| UniversalSigBypasser.asi | `1374ac9e894e45e802f983958599b7c396b11d2cf8fac9b4556bac73d453798b` |

## 后续优化可以考虑的方向

可首先合并外层 Python 包装的路径处理和启动提示，减少一个约 8MB 的包装程序；
其次研究把全局钩子的范围缩小到准确的游戏线程、增加注入成功/插件加载成功的可观测状态，
并梳理插件复制行为和路径字符编码。以上仅是后续改造方向，本次仍运行原始二进制。
游戏更新后，特征匹配和等待时机也需要重新验证。

静态分析不能证明迁移后的动态注入成功、当前游戏版本的 bypass 有效，或游戏内 pak
实际生效。这些运行验证留给用户。本地 `tools/loader-analysis` 保存了 Python
反汇编、四个文件的 PE 信息/字符串和三个原生文件的关键函数反汇编；证据不包含在发行包中。

## 单窗口启动器改造（2026-10-12）

替换 Game start.exe 的界面与控制逻辑，保留 MyCustomLoader.dll 和 ASI 的原始字节。
两个按钮直接设置可选 Anticensor 文件并执行启动，无额外选择窗口、支持作者或语言控件。
原函数 0x14004f400 的 0x14004f983 复制 plugins，0x14004f9b1 安装
WH_CBT(5, CBTProc, DLL, 0)，0x14004fcc9 ShellExecute 启动配置中的官方启动器。
0x14004fd07 检测游戏进程，0x14004fd28 等待 15000ms，
0x14004fd36 卸载钩子，然后 FreeLibrary。新界面以 Tk 消息循环保持钩子生命周期，
复用同一导出与等待时序，改用 Unicode Win32 API。
只确认启动序列完成，不将等待结束等同于实际插件注入成功。
已通过 9 项隔离测试；动态注入与游戏画面效果由用户验收。
