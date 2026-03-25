import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.py"


class RuntimeConfigTests(unittest.TestCase):
    def _load_config(self, env=None, config_path=CONFIG_PATH):
        previous_module = sys.modules.pop("config", None)

        def restore_module():
            sys.modules.pop("config", None)
            if previous_module is not None:
                sys.modules["config"] = previous_module

        self.addCleanup(restore_module)

        env_patcher = mock.patch.dict(os.environ, env or {}, clear=True)
        env_patcher.start()
        self.addCleanup(env_patcher.stop)

        spec = importlib.util.spec_from_file_location("config", config_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)

        module = importlib.util.module_from_spec(spec)
        sys.modules["config"] = module
        spec.loader.exec_module(module)
        return module

    def test_defaults_to_repo_data_dir(self):
        config = self._load_config()

        self.assertEqual(config.BASE_DIR, os.path.dirname(os.path.abspath(config.__file__)))
        self.assertEqual(config.DATA_DIR, os.path.join(config.BASE_DIR, "data"))
        self.assertEqual(config.TMP_DIR, os.path.join(config.DATA_DIR, "tmp"))
        self.assertEqual(config.ALLOWED_USERS_FILE, os.path.join(config.DATA_DIR, "allowed_users.txt"))
        self.assertEqual(config.USER_SETTINGS_FILE, os.path.join(config.DATA_DIR, "user_settings.json"))
        self.assertEqual(config.LOG_FILE, os.path.join(config.DATA_DIR, "strategy.log"))

    def test_keeps_data_dir_user_settings_path_even_if_legacy_root_file_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            config_path = base_dir / "config.py"
            config_path.write_text(CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8")
            (base_dir / "user_settings.json").write_text('{"legacy": true}', encoding="utf-8")

            config = self._load_config(config_path=config_path)

            self.assertEqual(config.BASE_DIR, str(base_dir))
            self.assertEqual(config.DATA_DIR, os.path.join(config.BASE_DIR, "data"))
            self.assertEqual(config.USER_SETTINGS_FILE, os.path.join(config.DATA_DIR, "user_settings.json"))
            self.assertNotEqual(config.USER_SETTINGS_FILE, os.path.join(config.BASE_DIR, "user_settings.json"))
            self.assertEqual(config.TMP_DIR, os.path.join(config.DATA_DIR, "tmp"))
            self.assertEqual(config.ALLOWED_USERS_FILE, os.path.join(config.DATA_DIR, "allowed_users.txt"))
            self.assertEqual(config.LOG_FILE, os.path.join(config.DATA_DIR, "strategy.log"))

    def test_honors_data_dir_override(self):
        config = self._load_config({"DATA_DIR": "/tmp/ltt-runtime"})

        self.assertEqual(config.DATA_DIR, "/tmp/ltt-runtime")
        self.assertEqual(config.TMP_DIR, os.path.join(config.DATA_DIR, "tmp"))
        self.assertEqual(config.ALLOWED_USERS_FILE, os.path.join(config.DATA_DIR, "allowed_users.txt"))
        self.assertEqual(config.USER_SETTINGS_FILE, os.path.join(config.DATA_DIR, "user_settings.json"))
        self.assertEqual(config.LOG_FILE, os.path.join(config.DATA_DIR, "strategy.log"))
