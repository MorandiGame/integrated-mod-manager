# 异环单窗口 Mod 启动器

`nte_launch_options.py` now replaces `Mod Loader/Game start.exe` itself. The original
outer `Mod注入器.exe` is restored to its plain forwarding role, so opening from IMM
shows only this panel. There are two buttons: **开启反虚化启动** and **不开反虚化启动**.
No author support or language controls are present. A checkbox **启用皮肤切换** selects the installed skin-only pak bundle independently of anticensor.

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

Validation: `python -m unittest discover -s loader -p 'test_*.py' -v` (14 tests).
Build with PyInstaller `--onefile --windowed --uac-admin --name "Game start"`.
Deploy to the existing external `Mod Loader` directory. No IMM rebuild is needed.
Runtime injection and in-game effect are tested by the user.

## Optional skin switching

Store the locally edited three-file bundle in `Optional Mods/SkinSwitch` next to
`Mod Loader`. `skin-switch.json` records the exact SHA-256 of `1_999_P.pak`,
`1_999_P.utoc`, and `1_999_P.ucas`. These user-provided compiled assets are not
distributed in this Git repository.

At startup the checkbox reflects the owned `HT/Content/Paks/Mods/IMM-SkinSwitch`
junction. Clicking either anticensor button applies the checkbox before the game
launch. Checked creates the junction; unchecked removes only that verified link.
Both options roll back if hooking or launching fails. A running game blocks
changes, unexpected target folders and modified bundle files are refused.
The existing Ultimate ASI Loader and bypass remain untouched.

The edited blueprint retains `-` for clothing and `=` for dye, removes the other
23 input bindings and the teleport/flight/actor/NPC/position-save execution paths,
and makes ReceiveTick inert. The original crosshair is hidden.
Pak structural and code validation passed; in-game switching remains user-tested.
