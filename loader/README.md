# 异环单窗口 Mod 启动器

`nte_launch_options.py` now replaces `Mod Loader/Game start.exe` itself. The original
outer `Mod注入器.exe` is restored to its plain forwarding role, so opening from IMM
shows only this panel. There are two buttons: **开启反虚化启动** and **不开反虚化启动**.
No author support or language controls are present.

One click configures the optional ASI, prepares the original loader plugins,
loads the original `MyCustomLoader.dll`, obtains its `CBTProc` export, installs the
original global `WH_CBT` hook (5, thread 0), and opens the official launcher from
`config.ini`. Tk keeps pumping Windows messages while waiting for the game.
After detecting HTGame, it waits the original 15 seconds before unhooking and
releasing the DLL. Keep the panel open until the completion message appears.
This status confirms the startup sequence, not that every ASI or pak loaded.

Anticensor is stored externally under adjacent `Optional Plugins` with its
original filename, relative location and SHA-256. The observed installation uses
`HT/Binaries/Win64/Anticensor.asi.asi`; the double extension is preserved. Turning it
off moves only this registered plugin outside the game; turning it on restores its
bytes. `cutils.dll` and existing matching bypass plugins remain unchanged.
Unknown conflicting plugins are rejected. Failed hook or launcher startup releases
the hook and restores the previous optional-plugin mode. A running game blocks mode
changes. Game paths and launcher settings remain in the existing config.ini.

Validation: `python -m unittest discover -s loader -p 'test_*.py' -v` (9 tests).
Build with PyInstaller `--onefile --windowed --uac-admin --name "Game start"`.
Deploy to the existing external `Mod Loader` directory. No IMM rebuild is needed.
Runtime injection and in-game effect are tested by the user.
