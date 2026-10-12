# Neverness To Everness / 异环

NTE uses Unreal pak packages and an external mod loader. It does not use XXMI,
3DMigoto INI preferences, disabled directory names, or F10 reload.

The source directory is an external library (default `F:\ntemod`). IMM keeps its
normal category/mod organization under its managed source subdirectory. The target
is the game's `HT\Content\Paks\Mods` directory. Enabling a mod creates an NTFS
junction under IMM's managed target subdirectory. Disabling removes only the
verified junction. The mod payload stays outside the game. Pak, utoc and ucas
companions stay together. Restart the game after changing already loaded pak files.

NTE has its own `configNTE.json`. Existing game keys, managed paths, config filenames,
XXMI launch behavior and preset storage remain compatible. Deployment replaces only
`integrated-mod-manager.exe` and adds `configNTE.json`; it does not run the installer.
This fork does not offer upstream executable updates, which would remove NTE support.

The online browser uses GameBanana game **23012**, Skins category **37906**, UI
category **43029** and Other/Misc category **37898**. The bundled snapshot contains
26 character categories; the existing API refresh, profile, search, download and
update-source machinery is reused. Archives containing several pak payloads are
split into separately selectable components/alternatives. Consult their original
documentation for main-file dependencies and mutually exclusive options.

The NTE Start button launches the original `Mod注入器.exe`. Its adjacent
`Mod Loader` directory must contain `Game start.exe`, `config.ini`,
`MyCustomLoader.dll`, and `plugins/UniversalSigBypasser.asi`. Configure the injector
path in the NTE settings panel. Loader binaries are user-provided and are not
distributed in this repository.

## Importing an existing export

`scripts/import_nte_mods.py` imports d3dxSkinManage exports into a new external IMM
library, checks ZIP member paths and extracted payload CRCs, preserves original
ZIPs, copies previews/documentation, and writes an import receipt. It refuses to
overwrite a destination. Each pak and its matching utoc/ucas files become a
separate disabled item. Chinese categories and source links are imported from
`export-index.json`; other IMM config files are not touched.

## Checks

`npm run build` verifies frontend types and generates the production UI.
`cargo test --manifest-path src-tauri/Cargo.toml --lib nte::tests` checks link
creation/removal, preservation of ordinary target folders, path traversal rejection,
invalid source/target rejection, pak recognition and variant companion handling.
`npm run tauri:build -- --no-bundle` builds the executable without running an installer.

These checks establish build/file behavior. Game loading, visuals, loader startup
and the full online download interaction require the user's runtime test.
