# 异环注入器启动选项

`nte_launch_options.py` replaces only the outer `Mod注入器.exe` launcher.
It displays **开启反虚化启动** and **不开反虚化启动**, configures the optional
Anticensor ASI, then opens the existing `Mod Loader/Game start.exe` with its original
working directory. The original Mod Loader panel remains responsible for launching
the game and injection. This wrapper does not alter the CBT hook or signature bypass.

The game directory is resolved from `Mod Loader/config.ini`'s `Launcher` setting.
Anticensor is registered outside the game under adjacent `Optional Plugins` with its
original filename, relative location and SHA-256. The observed installation uses
`HT/Binaries/Win64/Anticensor.asi.asi`; the double extension is preserved. Turning it
off moves this allowlisted plugin outside the game; turning it on restores its exact
bytes. `cutils.dll` and all other ASIs remain unchanged.

Do not switch while `HTGame.exe` is running. The wrapper rejects duplicated,
unrecognized or modified plugin files instead of overwriting them. A process-launch
failure restores the prior plugin state. The optional ASI is supplied locally by the
user and is not distributed in this repository.

Validation: `python -m unittest discover -s loader -p 'test_*.py' -v`.
Build with PyInstaller `--onefile --windowed --uac-admin --name Mod注入器`.
Deploy the resulting exe to the existing external loader directory; IMM's configured
injector path and the original inner loader binaries do not need to change.
