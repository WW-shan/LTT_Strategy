import errno
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils import prepare_runtime_state

STRATEGY_SIG_PATH = Path(__file__).resolve().parents[1] / "strategy_sig.py"
CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.py"


class RuntimeStateTests(unittest.TestCase):
    def write_file(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _load_strategy_sig(self, data_dir):
        previous_modules = {
            name: sys.modules.pop(name, None)
            for name in ("config", "strategy_sig", "exchange_utils")
        }

        def restore_modules():
            for name in ("config", "strategy_sig", "exchange_utils"):
                sys.modules.pop(name, None)
            for name, module in previous_modules.items():
                if module is not None:
                    sys.modules[name] = module

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

        exchange_utils = mock.Mock()
        exchange_utils.get_turtle_data = mock.Mock(return_value=mock.Mock(empty=True))
        sys.modules["exchange_utils"] = exchange_utils

        strategy_spec = importlib.util.spec_from_file_location("strategy_sig", STRATEGY_SIG_PATH)
        self.assertIsNotNone(strategy_spec)
        self.assertIsNotNone(strategy_spec.loader)
        strategy_module = importlib.util.module_from_spec(strategy_spec)
        sys.modules["strategy_sig"] = strategy_module
        strategy_spec.loader.exec_module(strategy_module)
        return config_module, strategy_module

    def test_prepare_runtime_state_creates_data_files_and_tmp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            data_dir = base_dir / "data"
            tmp_dir = data_dir / "tmp"
            allowed_users_file = data_dir / "allowed_users.txt"
            user_settings_file = data_dir / "user_settings.json"
            log_file = data_dir / "strategy.log"

            prepare_runtime_state(
                data_dir=str(data_dir),
                tmp_dir=str(tmp_dir),
                allowed_users_file=str(allowed_users_file),
                user_settings_file=str(user_settings_file),
                log_file=str(log_file),
                legacy_base_dir=str(base_dir),
            )

            self.assertTrue(data_dir.is_dir())
            self.assertTrue(tmp_dir.is_dir())
            self.assertTrue(allowed_users_file.is_file())
            self.assertTrue(user_settings_file.is_file())
            self.assertEqual(allowed_users_file.read_text(encoding="utf-8"), "")
            self.assertEqual(user_settings_file.read_text(encoding="utf-8"), "{}")
            self.assertFalse(log_file.exists())

    def test_prepare_runtime_state_migrates_without_overwriting_existing_targets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            data_dir = base_dir / "data"
            tmp_dir = data_dir / "tmp"
            allowed_users_file = data_dir / "allowed_users.txt"
            user_settings_file = data_dir / "user_settings.json"
            log_file = data_dir / "strategy.log"
            dedupe_target = tmp_dir / "last_can_biao_xiu_state_BTC.txt"

            legacy_allowed_users = base_dir / "allowed_users.txt"
            legacy_user_settings = base_dir / "user_settings.json"
            legacy_log_file = base_dir / "strategy.log"
            legacy_dedupe = base_dir / "tmp" / "last_can_biao_xiu_state_BTC.txt"

            self.write_file(legacy_allowed_users, "legacy users\n")
            self.write_file(legacy_user_settings, '{"legacy": true}')
            self.write_file(legacy_log_file, "legacy log\n")
            self.write_file(legacy_dedupe, "legacy dedupe\n")

            self.write_file(allowed_users_file, "current users\n")
            self.write_file(user_settings_file, '{"current": true}')
            self.write_file(log_file, "current log\n")
            self.write_file(dedupe_target, "current dedupe\n")

            prepare_runtime_state(
                data_dir=str(data_dir),
                tmp_dir=str(tmp_dir),
                allowed_users_file=str(allowed_users_file),
                user_settings_file=str(user_settings_file),
                log_file=str(log_file),
                legacy_base_dir=str(base_dir),
            )

            self.assertEqual(allowed_users_file.read_text(encoding="utf-8"), "current users\n")
            self.assertEqual(user_settings_file.read_text(encoding="utf-8"), '{"current": true}')
            self.assertEqual(log_file.read_text(encoding="utf-8"), "current log\n")
            self.assertEqual(dedupe_target.read_text(encoding="utf-8"), "current dedupe\n")

            self.assertEqual(legacy_allowed_users.read_text(encoding="utf-8"), "legacy users\n")
            self.assertEqual(legacy_user_settings.read_text(encoding="utf-8"), '{"legacy": true}')
            self.assertEqual(legacy_log_file.read_text(encoding="utf-8"), "legacy log\n")
            self.assertEqual(legacy_dedupe.read_text(encoding="utf-8"), "legacy dedupe\n")

    def test_prepare_runtime_state_handles_exdev_during_migration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            data_dir = base_dir / "data"
            tmp_dir = data_dir / "tmp"
            allowed_users_file = data_dir / "allowed_users.txt"
            user_settings_file = data_dir / "user_settings.json"
            log_file = data_dir / "strategy.log"
            dedupe_target = tmp_dir / "last_can_biao_xiu_state_BTC.txt"

            legacy_allowed_users = base_dir / "allowed_users.txt"
            legacy_user_settings = base_dir / "user_settings.json"
            legacy_log_file = base_dir / "strategy.log"
            legacy_dedupe = base_dir / "tmp" / "last_can_biao_xiu_state_BTC.txt"

            self.write_file(legacy_allowed_users, "legacy users\n")
            self.write_file(legacy_user_settings, '{"legacy": true}')
            self.write_file(legacy_log_file, "legacy log\n")
            self.write_file(legacy_dedupe, "legacy dedupe\n")

            with mock.patch("utils.os.replace", side_effect=OSError(errno.EXDEV, "cross-device link")):
                prepare_runtime_state(
                    data_dir=str(data_dir),
                    tmp_dir=str(tmp_dir),
                    allowed_users_file=str(allowed_users_file),
                    user_settings_file=str(user_settings_file),
                    log_file=str(log_file),
                    legacy_base_dir=str(base_dir),
                )

            self.assertEqual(allowed_users_file.read_text(encoding="utf-8"), "legacy users\n")
            self.assertEqual(user_settings_file.read_text(encoding="utf-8"), '{"legacy": true}')
            self.assertEqual(log_file.read_text(encoding="utf-8"), "legacy log\n")
            self.assertEqual(dedupe_target.read_text(encoding="utf-8"), "legacy dedupe\n")

            self.assertFalse(legacy_allowed_users.exists())
            self.assertFalse(legacy_user_settings.exists())
            self.assertFalse(legacy_log_file.exists())
            self.assertFalse(legacy_dedupe.exists())

    def test_strategy_sig_dedupe_state_uses_configured_tmp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config, strategy_sig = self._load_strategy_sig(tmpdir)
            expected_state_file = Path(config.TMP_DIR) / "last_can_biao_xiu_state_BTC.txt"
            expected_state_file.parent.mkdir(parents=True, exist_ok=True)

            strategy_sig.set_last_can_signal("BTC", "can,biao,xiu")

            self.assertTrue(expected_state_file.exists())
            self.assertEqual(expected_state_file.read_text(encoding="utf-8"), "can,biao,xiu")
            self.assertEqual(strategy_sig.get_last_can_signal("BTC"), "can,biao,xiu")
            self.assertEqual(
                strategy_sig.get_can_biao_xiu_state_path("BTC"),
                str(expected_state_file),
            )


if __name__ == "__main__":
    unittest.main()
