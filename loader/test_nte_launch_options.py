import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nte_launch_options import AnticensorController, register_plugin, start_existing_loader


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
                start_existing_loader(self.launch_root, False, self.controller)
        self.assertTrue(self.plugin.exists())

    def test_loader_start_failure_rolls_back_mode(self):
        with patch("nte_launch_options.game_is_running", return_value=False), patch("nte_launch_options.subprocess.Popen", side_effect=OSError("fixture")):
            with self.assertRaises(OSError):
                start_existing_loader(self.launch_root, False, self.controller)
        self.assertEqual(self.plugin.read_bytes(), b"original-optional-plugin")

    def test_loader_uses_original_working_directory(self):
        with patch("nte_launch_options.game_is_running", return_value=False), patch("nte_launch_options.subprocess.Popen") as spawn:
            start_existing_loader(self.launch_root, False, self.controller)
        self.assertFalse(self.plugin.exists())
        self.assertEqual(spawn.call_args.kwargs["cwd"], str(self.launch_root / "Mod Loader"))

    def test_refuses_manifest_path_traversal(self):
        manifest = self.storage / "anticensor.json"
        value = json.loads(manifest.read_text(encoding="utf-8"))
        value["game_relative_path"] = "../Anticensor.asi.asi"
        manifest.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaises(ValueError):
            AnticensorController(self.game, self.storage)


if __name__ == "__main__":
    unittest.main()
