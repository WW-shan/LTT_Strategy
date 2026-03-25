import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

CONFIG_PATH = REPO_ROOT / "config.py"
NOTIFIER_PATH = REPO_ROOT / "notifier.py"


class NotifierRuntimeTests(unittest.TestCase):
    def _load_modules(self, data_dir):
        previous_config = sys.modules.pop("config", None)
        previous_notifier = sys.modules.pop("notifier", None)

        def restore_modules():
            sys.modules.pop("notifier", None)
            sys.modules.pop("config", None)
            if previous_config is not None:
                sys.modules["config"] = previous_config
            if previous_notifier is not None:
                sys.modules["notifier"] = previous_notifier

        self.addCleanup(restore_modules)

        env_patcher = mock.patch.dict(os.environ, {"DATA_DIR": data_dir}, clear=True)
        env_patcher.start()
        self.addCleanup(env_patcher.stop)

        config_spec = importlib.util.spec_from_file_location("config", CONFIG_PATH)
        self.assertIsNotNone(config_spec)
        self.assertIsNotNone(config_spec.loader)
        config_module = importlib.util.module_from_spec(config_spec)
        sys.modules["config"] = config_module
        config_spec.loader.exec_module(config_module)

        notifier_spec = importlib.util.spec_from_file_location("notifier", NOTIFIER_PATH)
        self.assertIsNotNone(notifier_spec)
        self.assertIsNotNone(notifier_spec.loader)
        notifier_module = importlib.util.module_from_spec(notifier_spec)
        sys.modules["notifier"] = notifier_module
        notifier_spec.loader.exec_module(notifier_module)
        return config_module, notifier_module

    def test_allowed_user_persistence_uses_configured_allowed_users_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config, notifier = self._load_modules(tmpdir)
            allowed_users_path = Path(config.ALLOWED_USERS_FILE)

            self.assertEqual(allowed_users_path, Path(tmpdir) / "allowed_users.txt")
            self.assertFalse(allowed_users_path.exists())

            notifier.safe_write_user("1001")
            notifier.safe_write_user("1002")

            self.assertTrue(allowed_users_path.exists())
            self.assertEqual(notifier.load_allowed_users(), {"1001", "1002"})
            self.assertEqual(
                allowed_users_path.read_text(encoding="utf-8").splitlines(),
                ["1001", "1002"],
            )

            self.assertTrue(notifier.remove_user("1001"))
            self.assertEqual(notifier.load_allowed_users(), {"1002"})
            self.assertEqual(allowed_users_path.read_text(encoding="utf-8"), "1002\n")
            self.assertFalse((Path(tmpdir).parent / "allowed_users.txt").exists())


if __name__ == "__main__":
    unittest.main()
