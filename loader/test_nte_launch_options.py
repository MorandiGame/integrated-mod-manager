import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from nte_launch_options import AnticensorController, register_plugin, start_game, installation_root, NativeHook, SkinSwitchController, digest


class LaunchChoicesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.game = self.root / "Game/Binaries/Win64"
        self.game.mkdir(parents=True)
        self.plugin = self.game / "Anticensor.asi.asi"
        self.plugin.write_bytes(b"original-optional-plugin")
        (self.game / "cutils.dll").write_bytes(b"dependency")
        self.bypass = self.game / "UniversalSigBypasser.asi"
        self.bypass.write_bytes(b"keep-bypass")
        self.storage = self.root / "External/Optional Plugins"
        register_plugin(self.game, self.storage)
        self.controller = AnticensorController(self.game, self.storage)
        self.launch_root = self.root / "External"
        loader = self.launch_root / "Mod Loader"
        (loader / "plugins").mkdir(parents=True)
        for file in (loader / "Game start.exe", loader / "MyCustomLoader.dll", loader / "plugins/UniversalSigBypasser.asi"):
            file.write_bytes(b"existing-loader")
        self.launcher = self.root / "NTELauncher.exe"
        self.launcher.write_bytes(b"launcher")
        (loader / "config.ini").write_text("[Settings]\nLauncher=" + str(self.launcher), encoding="utf-8")

    def test_on_off_preserves_bytes_and_other_plugins(self):
        self.controller.set_enabled(False)
        self.assertFalse(self.plugin.exists())
        self.assertEqual(self.controller.source.read_bytes(), b"original-optional-plugin")
        self.controller.set_enabled(False)
        self.controller.set_enabled(True)
        self.controller.set_enabled(True)
        self.assertEqual(self.plugin.read_bytes(), b"original-optional-plugin")
        self.assertEqual(self.bypass.read_bytes(), b"keep-bypass")

    def test_refuses_unknown_replacement_and_duplicate_plugin(self):
        self.plugin.write_bytes(b"unknown-replacement")
        with self.assertRaises(ValueError):
            self.controller.set_enabled(False)
        self.assertEqual(self.plugin.read_bytes(), b"unknown-replacement")
        self.plugin.write_bytes(b"original-optional-plugin")
        other = self.game / "Anticensor.asi"
        other.write_bytes(b"second-plugin")
        with self.assertRaises(ValueError):
            self.controller.set_enabled(False)
        self.assertTrue(other.exists())

    def test_running_game_does_not_change_files(self):
        with patch("nte_launch_options.game_is_running", return_value=True):
            with self.assertRaises(ValueError):
                start_game(self.launch_root, False, self.controller)
        self.assertTrue(self.plugin.exists())

    def test_launcher_failure_releases_hook_and_rolls_back_mode(self):
        hook = Mock()
        with patch("nte_launch_options.game_is_running", return_value=False):
            with self.assertRaises(OSError):
                start_game(self.launch_root, False, self.controller,
                           hook_factory=Mock(return_value=hook), launch=Mock(side_effect=OSError("fixture")))
        hook.close.assert_called_once()
        self.assertEqual(self.plugin.read_bytes(), b"original-optional-plugin")

    def test_one_click_hooks_then_launches_official_without_second_panel(self):
        sequence = []
        hook = Mock()
        def install(dll):
            sequence.append("hook")
            self.assertEqual(dll, self.launch_root / "Mod Loader/MyCustomLoader.dll")
            return hook
        def launch(path):
            sequence.append("launch")
            self.assertEqual(path, self.launcher)
        with patch("nte_launch_options.game_is_running", return_value=False):
            result = start_game(self.launch_root, False, self.controller, install, launch)
        self.assertEqual(sequence, ["hook", "launch"])
        self.assertIs(result, hook)
        hook.close.assert_not_called()
        self.assertFalse(self.plugin.exists())
        self.assertEqual((self.game / "plugins/UniversalSigBypasser.asi").read_bytes(), b"existing-loader")
        self.assertEqual(self.bypass.read_bytes(), b"keep-bypass")

    def test_conflicting_bypass_refused_before_toggle(self):
        plugins = self.game / "plugins"
        plugins.mkdir()
        target = plugins / "UniversalSigBypasser.asi"
        target.write_bytes(b"other")
        with patch("nte_launch_options.game_is_running", return_value=False):
            with self.assertRaises(ValueError):
                start_game(self.launch_root, False, self.controller)
        self.assertTrue(self.plugin.exists())
        self.assertEqual(target.read_bytes(), b"other")

    def test_native_hook_uses_original_export_and_correct_64bit_handles(self):
        kernel, user = Mock(), Mock()
        kernel.LoadLibraryW.return_value = 0x100000000
        kernel.GetProcAddress.return_value = 0x100001000
        user.SetWindowsHookExW.return_value = 0x200000000
        user.UnhookWindowsHookEx.return_value = 1
        with patch("nte_launch_options.ctypes.WinDLL", side_effect=[kernel, user]):
            hook = NativeHook(Path("original.dll"))
        kernel.GetProcAddress.assert_called_once_with(0x100000000, b"CBTProc")
        user.SetWindowsHookExW.assert_called_once_with(5, 0x100001000, 0x100000000, 0)
        hook.close()
        hook.close()
        user.UnhookWindowsHookEx.assert_called_once_with(0x200000000)
        kernel.FreeLibrary.assert_called_once_with(0x100000000)

    def test_both_entry_paths_resolve_same_installation(self):
        self.assertEqual(installation_root(self.launch_root / "Mod Loader/Game start.exe"), self.launch_root)
        self.assertEqual(installation_root(self.launch_root / "Mod注入器.exe"), self.launch_root)

    def make_skin_controller(self):
        storage = self.launch_root / "Optional Mods/SkinSwitch"
        storage.mkdir(parents=True)
        hashes = {}
        for name in SkinSwitchController.FILENAMES:
            file = storage / name
            file.write_bytes(("fixture " + name).encode())
            hashes[name] = digest(file)
        (storage / "skin-switch.json").write_text(json.dumps({"files": hashes}), encoding="utf-8")
        return SkinSwitchController(self.game, storage)

    def test_skin_junction_roundtrip_preserves_source_and_other_mods(self):
        skin = self.make_skin_controller()
        other = skin.target.parent / "OtherMod"
        other.mkdir(parents=True)
        (other / "other.pak").write_bytes(b"untouched")
        with patch("nte_launch_options.game_is_running", return_value=False):
            skin.set_enabled(True)
            skin.set_enabled(True)
            self.assertTrue(skin.is_enabled())
            for name in skin.FILENAMES:
                self.assertEqual((skin.target / name).read_bytes(), (skin.source / name).read_bytes())
            skin.set_enabled(False)
            skin.set_enabled(False)
        self.assertFalse(skin.is_enabled())
        self.assertTrue(all((skin.source / n).is_file() for n in skin.FILENAMES))
        self.assertEqual((other / "other.pak").read_bytes(), b"untouched")

    def test_skin_refuses_modified_bundle_and_existing_regular_directory(self):
        skin = self.make_skin_controller()
        (skin.source / "1_999_P.pak").write_bytes(b"unknown")
        with patch("nte_launch_options.game_is_running", return_value=False):
            with self.assertRaises(ValueError):
                skin.set_enabled(True)
        skin = self.make_skin_controller_after_cleanup(skin)
        skin.target.mkdir(parents=True)
        (skin.target / "keep.txt").write_bytes(b"keep")
        with self.assertRaises(ValueError):
            skin.is_enabled()
        self.assertEqual((skin.target / "keep.txt").read_bytes(), b"keep")

    def make_skin_controller_after_cleanup(self, skin):
        hashes = {}
        for name in skin.FILENAMES:
            file = skin.source / name
            file.write_bytes(("fixture " + name).encode())
            hashes[name] = digest(file)
        (skin.source / "skin-switch.json").write_text(json.dumps({"files": hashes}), encoding="utf-8")
        return SkinSwitchController(self.game, skin.source)

    def test_skin_refuses_original_bundle_conflict(self):
        skin = self.make_skin_controller()
        skin.paks.mkdir(parents=True)
        (skin.paks / "1_999_P.pak").write_bytes(b"original")
        with patch("nte_launch_options.game_is_running", return_value=False):
            with self.assertRaises(ValueError):
                skin.set_enabled(True)
        self.assertFalse(skin.is_enabled())

    def test_skin_running_game_cannot_change_link(self):
        skin = self.make_skin_controller()
        with patch("nte_launch_options.game_is_running", return_value=True):
            with self.assertRaises(ValueError):
                skin.set_enabled(True)
        self.assertFalse(skin.is_enabled())

    def test_failed_launch_rolls_back_both_independent_options(self):
        skin = self.make_skin_controller()
        hook = Mock()
        with patch("nte_launch_options.game_is_running", return_value=False):
            with self.assertRaises(OSError):
                start_game(self.launch_root, False, self.controller,
                           hook_factory=Mock(return_value=hook), launch=Mock(side_effect=OSError("fixture")),
                           skin_controller=skin, skin_enabled=True)
        self.assertTrue(self.plugin.exists())
        self.assertFalse(skin.is_enabled())
        hook.close.assert_called_once()

    def test_refuses_manifest_path_traversal(self):
        manifest = self.storage / "anticensor.json"
        value = json.loads(manifest.read_text(encoding="utf-8"))
        value["game_relative_path"] = "../Anticensor.asi.asi"
        manifest.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaises(ValueError):
            AnticensorController(self.game, self.storage)


if __name__ == "__main__":
    unittest.main()
