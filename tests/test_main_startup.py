import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


MAIN_PATH = Path(__file__).resolve().parents[1] / "main.py"


class MainStartupTests(unittest.TestCase):
    def _load_main_module(self):
        module_names = ["config", "exchange_utils", "strategy_sig", "notifier", "utils", "schedule"]
        previous_modules = {name: sys.modules.pop(name, None) for name in module_names}

        def restore_modules():
            for name in module_names:
                sys.modules.pop(name, None)
            for name, module in previous_modules.items():
                if module is not None:
                    sys.modules[name] = module

        self.addCleanup(restore_modules)

        config = types.ModuleType("config")
        config.LOGLEVEL = "INFO"
        config.TIMEFRAMES = ["1h", "1d"]
        config.MAX_WORKERS = 2
        config.DC_PERIOD = 28
        config.SYMBOLS = []
        config.MA_LONG = 200
        config.DATA_DIR = "/tmp/ltt-data"
        config.TMP_DIR = "/tmp/ltt-data/tmp"
        config.ALLOWED_USERS_FILE = "/tmp/ltt-data/allowed_users.txt"
        config.USER_SETTINGS_FILE = "/tmp/ltt-data/user_settings.json"
        config.LOG_FILE = "/tmp/ltt-data/strategy.log"
        config.BASE_DIR = "/tmp/ltt-base"

        exchange_utils = types.ModuleType("exchange_utils")
        exchange_utils.get_data = lambda *args, **kwargs: None
        exchange_utils.get_all_usdt_swap_symbols = lambda: []
        exchange_utils.warmup_connection = lambda: None

        strategy_sig = types.ModuleType("strategy_sig")
        strategy_sig.check_signal = lambda *args, **kwargs: []
        strategy_sig.check_turtle_signal = lambda *args, **kwargs: []
        strategy_sig.check_can_biao_xiu_signal = lambda *args, **kwargs: []

        notifier = types.ModuleType("notifier")
        notifier.monitor_new_users = lambda: None
        notifier.send_telegram_message = lambda message: None
        notifier.set_bot_commands = lambda: None
        notifier.rsi6_summary = lambda signals: None
        notifier.handle_signals = lambda signal, rsi6_signals=None: None

        utils = types.ModuleType("utils")
        utils.prepare_runtime_state = lambda **kwargs: None

        class _ScheduledJob:
            def __init__(self, interval):
                self.interval = interval
                self.callback = None

            @property
            def minutes(self):
                return self

            def do(self, callback):
                self.callback = callback
                return callback

        schedule = types.ModuleType("schedule")
        schedule.every = lambda interval: _ScheduledJob(interval)
        schedule.run_pending = lambda: None

        sys.modules["config"] = config
        sys.modules["exchange_utils"] = exchange_utils
        sys.modules["strategy_sig"] = strategy_sig
        sys.modules["notifier"] = notifier
        sys.modules["utils"] = utils
        sys.modules["schedule"] = schedule

        spec = importlib.util.spec_from_file_location("main_under_test", MAIN_PATH)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_main_module_defines_callable_main_and_entrypoint_guard(self):
        source = MAIN_PATH.read_text(encoding="utf-8")

        self.assertIn("def main(", source)
        self.assertIn('if __name__ == "__main__":', source)

        module = self._load_main_module()
        self.assertTrue(callable(module.main))

    def test_main_prepares_runtime_state_before_startup_side_effects(self):
        module = self._load_main_module()
        events = []

        class DummyThread:
            def __init__(self, *args, **kwargs):
                events.append(("thread_init", kwargs.get("target")))

            def start(self):
                events.append(("thread_start", None))

        class ScheduledJob:
            def __init__(self, interval):
                events.append(("schedule.every", interval))

            @property
            def minutes(self):
                return self

            def do(self, callback):
                events.append(("schedule.do", callback))
                return callback

        job_mock = mock.Mock(side_effect=lambda: events.append(("job", None)))

        with mock.patch.object(module, "prepare_runtime_state", side_effect=lambda **kwargs: events.append(("prepare_runtime_state", kwargs))), \
             mock.patch.object(module.logging, "FileHandler", side_effect=lambda path: events.append(("logging.FileHandler", path)) or mock.sentinel.file_handler), \
             mock.patch.object(module.logging, "basicConfig", side_effect=lambda **kwargs: events.append(("logging.basicConfig", kwargs))), \
             mock.patch.object(module.logging, "info", side_effect=lambda message: events.append(("logging.info", message))), \
             mock.patch.object(module.threading, "Thread", side_effect=lambda *args, **kwargs: DummyThread(*args, **kwargs)), \
             mock.patch.object(module, "set_bot_commands", side_effect=lambda: events.append(("set_bot_commands", None))), \
             mock.patch.object(module, "send_telegram_message", side_effect=lambda message: events.append(("send_telegram_message", message))), \
             mock.patch.object(module.schedule, "every", side_effect=lambda interval: ScheduledJob(interval)), \
             mock.patch.object(module.schedule, "run_pending", side_effect=AssertionError("run_loop=False should not poll the scheduler")), \
             mock.patch.object(module.time, "sleep", side_effect=AssertionError("run_loop=False should not sleep")), \
             mock.patch.object(module, "job", job_mock):
            module.main(run_loop=False)

        event_names = [name for name, _ in events]
        prepare_index = event_names.index("prepare_runtime_state")

        for later_event in [
            "logging.FileHandler",
            "logging.basicConfig",
            "thread_init",
            "thread_start",
            "set_bot_commands",
            "logging.info",
            "send_telegram_message",
            "schedule.every",
            "schedule.do",
            "job",
        ]:
            self.assertLess(prepare_index, event_names.index(later_event))

        prepare_call = next(payload for name, payload in events if name == "prepare_runtime_state")
        self.assertEqual(prepare_call["data_dir"], module.DATA_DIR)
        self.assertEqual(prepare_call["tmp_dir"], module.TMP_DIR)
        self.assertEqual(prepare_call["allowed_users_file"], module.ALLOWED_USERS_FILE)
        self.assertEqual(prepare_call["user_settings_file"], module.USER_SETTINGS_FILE)
        self.assertEqual(prepare_call["log_file"], module.LOG_FILE)
        self.assertEqual(prepare_call["legacy_base_dir"], module.BASE_DIR)

        file_handler_path = next(payload for name, payload in events if name == "logging.FileHandler")
        self.assertEqual(file_handler_path, module.LOG_FILE)
        self.assertIn(("send_telegram_message", "策略开始"), events)
        self.assertIn(("thread_start", None), events)
        self.assertIn(("schedule.every", 60), events)
        self.assertIn(("schedule.do", job_mock), events)
        job_mock.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
