# ClawCloud Docker Runtime Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify all mutable runtime files under a single `data` directory model that works for ClawCloud Docker deployment, local/VPS Docker Compose deployment, and direct local `python main.py` runs without losing existing user data.

**Architecture:** Keep the existing single-process Python bot and current Docker entrypoint flow, but move all runtime path decisions into `config.py` and prepare/migrate runtime state in one shared bootstrap path. Container builds will explicitly default to `/app/data`, while local direct execution will default to `./data`, and deployment/docs will be updated so Docker, Compose, and local runs all describe the same runtime model.

**Tech Stack:** Python 3, stdlib `unittest`, shell entrypoint, Docker, Docker Compose, Markdown docs

---

## File Structure

- `config.py` — single source of truth for mutable runtime paths (`DATA_DIR`, `TMP_DIR`, `ALLOWED_USERS_FILE`, `USER_SETTINGS_FILE`, `LOG_FILE`)
- `utils.py` — file/directory bootstrap plus one-time legacy migration helpers for root-path runtime files
- `main.py` — startup bootstrap and log file wiring before the bot enters its existing scheduling loop
- `notifier.py` — subscription/user-settings persistence, switched from hard-coded root files to config paths
- `strategy_sig.py` — dedupe-state file path, switched from `tmp/...` to `TMP_DIR/...`
- `docker-entrypoint.sh` — container env validation + runtime directory creation; it must not pre-create files that would block shared Python migration logic
- `Dockerfile` — container default `DATA_DIR=/app/data`
- `docker-compose.yml` — local/VPS mount stays `./data:/app/data`; Compose pins `DATA_DIR=/app/data` in `environment:` so `.env` cannot drift runtime writes outside the mounted volume
- `.dockerignore` — exclude `.env` and `data/` from build context
- `.env.example` — document required vars and optional `DATA_DIR` for Docker/ClawCloud and direct local runs, but not for Compose
- `README.md` — separate ClawCloud, Docker Compose, and local Python runbooks; remove root-level runtime-file guidance
- `tests/test_runtime_config.py` — config path regression tests
- `tests/test_runtime_state.py` — bootstrap/migration regression tests
- `tests/test_notifier_runtime.py` — notifier persistence regression tests for `allowed_users.txt`
- `tests/test_main_startup.py` — startup wiring regression tests for `main.py` bootstrap order and side-effect isolation
- `tests/test_deployment_files.py` — Docker/Compose/file-layout regression tests
- `tests/test_readme_docs.py` — README deployment doc regression tests

Because this repo has no test framework today, use stdlib `unittest` under `tests/` so we do not add new production dependencies.

---

### Task 1: Centralize runtime path configuration

**Files:**
- Create: `tests/test_runtime_config.py`
- Modify: `config.py:1-19`

- [ ] **Step 1: Write the failing config-path test**

```python
import importlib
import os
import unittest
from unittest import mock


class RuntimeConfigTests(unittest.TestCase):
    def _reload_config(self):
        import config
        return importlib.reload(config)

    def test_defaults_to_repo_data_dir(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            config = self._reload_config()
        self.assertTrue(config.DATA_DIR.endswith("data"))
        self.assertTrue(config.TMP_DIR.endswith("data/tmp"))
        self.assertTrue(config.ALLOWED_USERS_FILE.endswith("data/allowed_users.txt"))
        self.assertTrue(config.USER_SETTINGS_FILE.endswith("data/user_settings.json"))
        self.assertTrue(config.LOG_FILE.endswith("data/strategy.log"))

    def test_honors_data_dir_override(self):
        with mock.patch.dict(os.environ, {"DATA_DIR": "/tmp/ltt-runtime"}, clear=True):
            config = self._reload_config()
        self.assertEqual(config.DATA_DIR, "/tmp/ltt-runtime")
        self.assertEqual(config.TMP_DIR, "/tmp/ltt-runtime/tmp")
        self.assertEqual(config.ALLOWED_USERS_FILE, "/tmp/ltt-runtime/allowed_users.txt")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest discover -s tests -p 'test_runtime_config.py' -v`
Expected: FAIL with `AttributeError: module 'config' has no attribute 'DATA_DIR'`.

- [ ] **Step 3: Implement the minimal runtime path constants**

```python
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.getenv('DATA_DIR', os.path.join(BASE_DIR, 'data'))
TMP_DIR = os.path.join(DATA_DIR, 'tmp')
ALLOWED_USERS_FILE = os.path.join(DATA_DIR, 'allowed_users.txt')
USER_SETTINGS_FILE = os.path.join(DATA_DIR, 'user_settings.json')
LOG_FILE = os.path.join(DATA_DIR, 'strategy.log')

LOGLEVEL = os.getenv('LOGLEVEL', 'INFO').upper()
TG_BOT_TOKEN = os.getenv('TG_BOT_TOKEN', '')
TG_CHAT_ID = os.getenv('TG_CHAT_ID', '')
SYMBOLS = ['BTC/USDT:USDT']
TIMEFRAMES = ['1h', '4h', '1d']
DC_PERIOD = 28
MAX_WORKERS = int(os.getenv('MAX_WORKERS', 8))
MA_FAST = 5
MA_MID = 10
MA_SLOW = 20
MA_LONG = 200
MAX_MSG_LEN = 4096
SUBSCRIBE_PASSWORD = os.getenv('SUBSCRIBE_PASSWORD', '')
DEFAULT_USER_SETTINGS = {
    "enabled_timeframes": ["1h", "4h", "1d"],
    "enabled_signals": ["turtle_buy", "turtle_sell", "can_biao_xiu", "five_down"],
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m unittest discover -s tests -p 'test_runtime_config.py' -v`
Expected: PASS with 2 tests, 0 failures.

- [ ] **Step 5: Prepare the checkpoint commit**

```bash
git add config.py tests/test_runtime_config.py
git commit -m "refactor: centralize runtime path configuration"
```

Use this commit only if the user has asked you to create a commit at this checkpoint.

---

### Task 2: Add shared runtime bootstrap and legacy migration helpers

**Files:**
- Create: `tests/test_runtime_state.py`
- Modify: `utils.py:1-15`

- [ ] **Step 1: Write the failing runtime-state test**

```python
import errno
import os
import tempfile
import unittest
from unittest import mock

from utils import prepare_runtime_state


class RuntimeStateTests(unittest.TestCase):
    def test_prepare_runtime_state_creates_data_files_and_tmp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = os.path.join(tmpdir, 'data')
            prepare_runtime_state(
                data_dir=data_dir,
                tmp_dir=os.path.join(data_dir, 'tmp'),
                allowed_users_file=os.path.join(data_dir, 'allowed_users.txt'),
                user_settings_file=os.path.join(data_dir, 'user_settings.json'),
                log_file=os.path.join(data_dir, 'strategy.log'),
                legacy_allowed_users_file=os.path.join(tmpdir, 'allowed_users.txt'),
                legacy_user_settings_file=os.path.join(tmpdir, 'user_settings.json'),
                legacy_tmp_dir=os.path.join(tmpdir, 'tmp'),
                legacy_log_file=os.path.join(tmpdir, 'strategy.log'),
            )
            self.assertTrue(os.path.isdir(os.path.join(data_dir, 'tmp')))
            self.assertTrue(os.path.isfile(os.path.join(data_dir, 'allowed_users.txt')))
            self.assertTrue(os.path.isfile(os.path.join(data_dir, 'user_settings.json')))

    def test_prepare_runtime_state_migrates_legacy_files_without_overwriting_targets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            legacy_allowed = os.path.join(tmpdir, 'allowed_users.txt')
            legacy_settings = os.path.join(tmpdir, 'user_settings.json')
            legacy_tmp_dir = os.path.join(tmpdir, 'tmp')
            legacy_log = os.path.join(tmpdir, 'strategy.log')
            os.makedirs(legacy_tmp_dir, exist_ok=True)
            with open(legacy_allowed, 'w', encoding='utf-8') as fh:
                fh.write('10001\n')
            with open(legacy_settings, 'w', encoding='utf-8') as fh:
                fh.write('{"10001": {}}')
            with open(os.path.join(legacy_tmp_dir, 'last_can_biao_xiu_state_BTC.txt'), 'w', encoding='utf-8') as fh:
                fh.write('legacy-state')
            with open(legacy_log, 'w', encoding='utf-8') as fh:
                fh.write('legacy-log')

            data_dir = os.path.join(tmpdir, 'data')
            target_allowed = os.path.join(data_dir, 'allowed_users.txt')
            target_settings = os.path.join(data_dir, 'user_settings.json')
            target_tmp_dir = os.path.join(data_dir, 'tmp')
            target_log = os.path.join(data_dir, 'strategy.log')
            os.makedirs(target_tmp_dir, exist_ok=True)
            with open(target_allowed, 'w', encoding='utf-8') as fh:
                fh.write('keep-me\n')
            with open(target_settings, 'w', encoding='utf-8') as fh:
                fh.write('{"keep": true}')
            with open(os.path.join(target_tmp_dir, 'last_can_biao_xiu_state_BTC.txt'), 'w', encoding='utf-8') as fh:
                fh.write('keep-target-state')
            with open(target_log, 'w', encoding='utf-8') as fh:
                fh.write('keep-target-log')

            prepare_runtime_state(
                data_dir=data_dir,
                tmp_dir=target_tmp_dir,
                allowed_users_file=target_allowed,
                user_settings_file=target_settings,
                log_file=target_log,
                legacy_allowed_users_file=legacy_allowed,
                legacy_user_settings_file=legacy_settings,
                legacy_tmp_dir=legacy_tmp_dir,
                legacy_log_file=legacy_log,
            )

            with open(target_allowed, 'r', encoding='utf-8') as fh:
                self.assertEqual(fh.read(), 'keep-me\n')
            with open(target_settings, 'r', encoding='utf-8') as fh:
                self.assertEqual(fh.read(), '{"keep": true}')
            with open(os.path.join(target_tmp_dir, 'last_can_biao_xiu_state_BTC.txt'), 'r', encoding='utf-8') as fh:
                self.assertEqual(fh.read(), 'keep-target-state')
            with open(target_log, 'r', encoding='utf-8') as fh:
                self.assertEqual(fh.read(), 'keep-target-log')

    def test_prepare_runtime_state_handles_cross_device_migration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            legacy_allowed = os.path.join(tmpdir, 'allowed_users.txt')
            with open(legacy_allowed, 'w', encoding='utf-8') as fh:
                fh.write('10001\n')
            data_dir = os.path.join(tmpdir, 'data')
            target_allowed = os.path.join(data_dir, 'allowed_users.txt')

            with mock.patch('utils.os.replace', side_effect=OSError(errno.EXDEV, 'cross-device link')):
                prepare_runtime_state(
                    data_dir=data_dir,
                    tmp_dir=os.path.join(data_dir, 'tmp'),
                    allowed_users_file=target_allowed,
                    user_settings_file=os.path.join(data_dir, 'user_settings.json'),
                    log_file=os.path.join(data_dir, 'strategy.log'),
                    legacy_allowed_users_file=legacy_allowed,
                    legacy_user_settings_file=os.path.join(tmpdir, 'user_settings.json'),
                    legacy_tmp_dir=os.path.join(tmpdir, 'tmp'),
                    legacy_log_file=os.path.join(tmpdir, 'strategy.log'),
                )

            with open(target_allowed, 'r', encoding='utf-8') as fh:
                self.assertEqual(fh.read(), '10001\n')
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest discover -s tests -p 'test_runtime_state.py' -v`
Expected: FAIL with `ImportError: cannot import name 'prepare_runtime_state' from 'utils'`.

- [ ] **Step 3: Implement the minimal bootstrap + migration helpers**

```python
import errno
import os
import shutil


def ensure_dir_exists(directory):
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


def ensure_file_exists(file_path):
    if not os.path.exists(file_path):
        parent_dir = os.path.dirname(file_path)
        if parent_dir:
            ensure_dir_exists(parent_dir)
        with open(file_path, 'w', encoding='utf-8') as f:
            if file_path.endswith('.json'):
                f.write('{}')
            else:
                f.write('')


def move_path_if_missing(legacy_path, target_path):
    if not legacy_path or legacy_path == target_path:
        return
    if not os.path.exists(legacy_path) or os.path.exists(target_path):
        return
    ensure_dir_exists(os.path.dirname(target_path))
    try:
        os.replace(legacy_path, target_path)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        shutil.copy2(legacy_path, target_path)
        os.remove(legacy_path)


def migrate_tmp_state_files(legacy_tmp_dir, target_tmp_dir):
    if not legacy_tmp_dir or not os.path.isdir(legacy_tmp_dir):
        return
    ensure_dir_exists(target_tmp_dir)
    for name in os.listdir(legacy_tmp_dir):
        if not name.startswith('last_can_biao_xiu_state_') or not name.endswith('.txt'):
            continue
        move_path_if_missing(
            os.path.join(legacy_tmp_dir, name),
            os.path.join(target_tmp_dir, name),
        )


def prepare_runtime_state(
    *,
    data_dir,
    tmp_dir,
    allowed_users_file,
    user_settings_file,
    log_file,
    legacy_allowed_users_file,
    legacy_user_settings_file,
    legacy_tmp_dir,
    legacy_log_file,
):
    ensure_dir_exists(data_dir)
    ensure_dir_exists(tmp_dir)
    move_path_if_missing(legacy_allowed_users_file, allowed_users_file)
    move_path_if_missing(legacy_user_settings_file, user_settings_file)
    move_path_if_missing(legacy_log_file, log_file)
    migrate_tmp_state_files(legacy_tmp_dir, tmp_dir)
    ensure_file_exists(allowed_users_file)
    ensure_file_exists(user_settings_file)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m unittest discover -s tests -p 'test_runtime_state.py' -v`
Expected: PASS with 3 tests, 0 failures.

- [ ] **Step 5: Prepare the checkpoint commit**

```bash
git add utils.py tests/test_runtime_state.py
git commit -m "feat: add runtime state bootstrap and migration"
```

Use this commit only if the user has asked you to create a commit at this checkpoint.

---

### Task 3: Wire runtime consumers and the real startup path through the unified data directory

**Files:**
- Create: `tests/test_main_startup.py`
- Create: `tests/test_notifier_runtime.py`
- Modify: `main.py:1-81`
- Modify: `notifier.py:1-187`
- Modify: `strategy_sig.py:1-399`
- Modify: `tests/test_runtime_state.py`

- [ ] **Step 1: Write the failing startup-entrypoint structure test**

Create `tests/test_main_startup.py` with:

```python
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MainStartupStructureTests(unittest.TestCase):
    def test_main_py_exposes_callable_entrypoint(self):
        text = (ROOT / 'main.py').read_text(encoding='utf-8')
        self.assertIn('def main(', text)
        self.assertIn('if __name__ == "__main__":', text)
```

- [ ] **Step 2: Write the failing notifier persistence regression test**

Create `tests/test_notifier_runtime.py` with:

```python
import importlib
import os
import tempfile
import unittest
from unittest import mock


class NotifierRuntimeTests(unittest.TestCase):
    def test_notifier_uses_configured_allowed_users_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(os.environ, {'DATA_DIR': tmpdir}, clear=True):
                import config
                import notifier
                importlib.reload(config)
                notifier = importlib.reload(notifier)

                notifier.safe_write_user('10001')
                self.assertTrue(os.path.exists(os.path.join(tmpdir, 'allowed_users.txt')))
                self.assertEqual(notifier.load_allowed_users(), {'10001'})
                self.assertTrue(notifier.remove_user('10001'))
                self.assertEqual(notifier.load_allowed_users(), set())
```

- [ ] **Step 3: Extend the failing test for the signal-state path**

Add this test to `tests/test_runtime_state.py`:

```python
from unittest import mock
import strategy_sig

    def test_can_signal_state_uses_configured_tmp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.object(strategy_sig, 'TMP_DIR', tmpdir):
                strategy_sig.set_last_can_signal('BTC', 'state-v1')
                self.assertEqual(strategy_sig.get_last_can_signal('BTC'), 'state-v1')
                self.assertTrue(
                    os.path.exists(os.path.join(tmpdir, 'last_can_biao_xiu_state_BTC.txt'))
                )
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `python3 -m unittest discover -s tests -p 'test_main_startup.py' -v && python3 -m unittest discover -s tests -p 'test_notifier_runtime.py' -v && python3 -m unittest discover -s tests -p 'test_runtime_state.py' -v`
Expected: `test_main_py_exposes_callable_entrypoint` FAILS because `main.py` has no callable entrypoint yet; the notifier test FAILS because `notifier.py` still targets the old root file path; the runtime-state test FAILS because `strategy_sig` still writes to hard-coded `tmp/last_can_biao_xiu_state_*.txt`.

- [ ] **Step 5: Implement the minimal wiring changes**

Update `notifier.py` so the subscription file path comes from config instead of a hard-coded root file:

```python
from config import (
    TG_BOT_TOKEN,
    TG_CHAT_ID,
    SUBSCRIBE_PASSWORD,
    DEFAULT_USER_SETTINGS,
    USER_SETTINGS_FILE,
    ALLOWED_USERS_FILE,
    TIMEFRAMES,
    MAX_MSG_LEN,
)

USER_FILE = ALLOWED_USERS_FILE
```

Update `strategy_sig.py` so dedupe state writes into `TMP_DIR`:

```python
from config import DC_PERIOD, MA_FAST, MA_MID, MA_SLOW, MA_LONG, TMP_DIR


def get_can_signal_state_path(symbol_short):
    return os.path.join(TMP_DIR, f"last_can_biao_xiu_state_{symbol_short}.txt")


def get_last_can_signal(symbol_short):
    fname = get_can_signal_state_path(symbol_short)
    if os.path.exists(fname):
        with open(fname, "r", encoding='utf-8') as f:
            return f.read().strip()
    return None


def set_last_can_signal(symbol_short, signal_state):
    os.makedirs(TMP_DIR, exist_ok=True)
    fname = get_can_signal_state_path(symbol_short)
    with open(fname, "w", encoding='utf-8') as f:
        f.write(str(signal_state))
```

Refactor `main.py` so startup becomes a callable path and runtime state is prepared before logging and side effects:

```python
import logging
import schedule
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from config import (
    LOGLEVEL,
    TIMEFRAMES,
    MAX_WORKERS,
    DC_PERIOD,
    SYMBOLS,
    MA_LONG,
    DATA_DIR,
    TMP_DIR,
    ALLOWED_USERS_FILE,
    USER_SETTINGS_FILE,
    LOG_FILE,
)
from exchange_utils import get_data, get_all_usdt_swap_symbols, warmup_connection
from strategy_sig import check_signal, check_turtle_signal, check_can_biao_xiu_signal
from notifier import monitor_new_users, send_telegram_message, set_bot_commands, rsi6_summary, handle_signals
from utils import prepare_runtime_state


def configure_logging():
    logging.basicConfig(
        level=getattr(logging, LOGLEVEL),
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(),
        ],
    )


def main(run_loop=True):
    prepare_runtime_state(
        data_dir=DATA_DIR,
        tmp_dir=TMP_DIR,
        allowed_users_file=ALLOWED_USERS_FILE,
        user_settings_file=USER_SETTINGS_FILE,
        log_file=LOG_FILE,
        legacy_allowed_users_file='allowed_users.txt',
        legacy_user_settings_file='user_settings.json',
        legacy_tmp_dir='tmp',
        legacy_log_file='strategy.log',
    )
    configure_logging()
    threading.Thread(target=monitor_new_users, daemon=True).start()
    set_bot_commands()
    logging.info("策略开始")
    send_telegram_message("策略开始")
    schedule.every(60).minutes.do(job)
    job()
    if run_loop:
        while True:
            schedule.run_pending()
            time.sleep(0.1)


if __name__ == "__main__":
    main()
```

Remove the old top-level startup side effects and the old `ensure_dir_exists("tmp")`, `ensure_file_exists("allowed_users.txt")`, and `ensure_file_exists(USER_SETTINGS_FILE)` bootstrap calls from `main.py`; they are now redundant.

- [ ] **Step 6: Upgrade `tests/test_main_startup.py` to a real startup-order regression test**

Replace the structure-only test with:

```python
import unittest
from unittest import mock

import main


class MainStartupTests(unittest.TestCase):
    @mock.patch('main.job')
    @mock.patch('main.schedule.every')
    @mock.patch('main.send_telegram_message')
    @mock.patch('main.set_bot_commands')
    @mock.patch('main.threading.Thread')
    @mock.patch('main.logging.StreamHandler')
    @mock.patch('main.logging.FileHandler')
    @mock.patch('main.logging.basicConfig')
    @mock.patch('main.prepare_runtime_state')
    def test_main_prepares_runtime_state_before_logging_and_side_effects(
        self,
        prepare_runtime_state,
        basic_config,
        file_handler,
        _stream_handler,
        thread_cls,
        set_bot_commands,
        send_telegram_message,
        schedule_every,
        job,
    ):
        call_order = []

        prepare_runtime_state.side_effect = lambda **kwargs: call_order.append('prepare_runtime_state')
        file_handler.side_effect = lambda *args, **kwargs: call_order.append('file_handler') or object()
        basic_config.side_effect = lambda **kwargs: call_order.append('basic_config')
        thread_cls.return_value.start.side_effect = lambda: call_order.append('thread_start')
        set_bot_commands.side_effect = lambda: call_order.append('set_bot_commands')
        send_telegram_message.side_effect = lambda *args, **kwargs: call_order.append('send_telegram_message')
        schedule_every.return_value.minutes.do.side_effect = lambda fn: call_order.append('schedule_job')
        job.side_effect = lambda: call_order.append('job')

        main.main(run_loop=False)

        self.assertLess(call_order.index('prepare_runtime_state'), call_order.index('file_handler'))
        self.assertLess(call_order.index('prepare_runtime_state'), call_order.index('set_bot_commands'))
        self.assertLess(call_order.index('prepare_runtime_state'), call_order.index('send_telegram_message'))
        self.assertLess(call_order.index('prepare_runtime_state'), call_order.index('job'))
```

- [ ] **Step 7: Run the tests and syntax verification**

Run: `python3 -m unittest discover -s tests -p 'test_main_startup.py' -v && python3 -m unittest discover -s tests -p 'test_notifier_runtime.py' -v && python3 -m unittest discover -s tests -p 'test_runtime_state.py' -v && python3 -m py_compile main.py notifier.py strategy_sig.py`
Expected: PASS for startup-order, notifier-persistence, and runtime-state tests and no `py_compile` output.

- [ ] **Step 8: Prepare the checkpoint commit**

```bash
git add main.py notifier.py strategy_sig.py tests/test_main_startup.py tests/test_notifier_runtime.py tests/test_runtime_state.py
git commit -m "refactor: route runtime files through startup bootstrap"
```

Use this commit only if the user has asked you to create a commit at this checkpoint.

---

### Task 4: Align container bootstrap and Docker build inputs with the new runtime model

**Files:**
- Create: `tests/test_deployment_files.py`
- Modify: `docker-entrypoint.sh:1-26`
- Modify: `Dockerfile:1-14`
- Modify: `docker-compose.yml:1-16`
- Modify: `.dockerignore:1-17`
- Modify: `.env.example:1-13`

- [ ] **Step 1: Write the failing deployment-file tests**

```python
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DeploymentFileTests(unittest.TestCase):
    def test_dockerfile_sets_default_container_data_dir(self):
        dockerfile = (ROOT / 'Dockerfile').read_text(encoding='utf-8')
        self.assertIn('DATA_DIR=/app/data', dockerfile)

    def test_entrypoint_bootstraps_data_dir_without_symlinks(self):
        entrypoint = (ROOT / 'docker-entrypoint.sh').read_text(encoding='utf-8')
        self.assertIn('DATA_DIR="${DATA_DIR:-/app/data}"', entrypoint)
        self.assertIn('mkdir -p "$DATA_DIR" "$DATA_DIR/tmp"', entrypoint)
        self.assertNotIn('ln -sf', entrypoint)

    def test_compose_mounts_data_dir_and_pins_runtime_path(self):
        compose = (ROOT / 'docker-compose.yml').read_text(encoding='utf-8')
        self.assertIn('./data:/app/data', compose)
        self.assertIn('DATA_DIR: /app/data', compose)

    def test_dockerignore_excludes_runtime_state_from_build_context(self):
        dockerignore = (ROOT / '.dockerignore').read_text(encoding='utf-8')
        self.assertIn('.env', dockerignore)
        self.assertIn('data/', dockerignore)
        self.assertIn('allowed_users.txt', dockerignore)
        self.assertIn('user_settings.json', dockerignore)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest discover -s tests -p 'test_deployment_files.py' -v`
Expected: FAIL because the current files still use symlinks, do not export `DATA_DIR`, and do not ignore `data/` in `.dockerignore`.

- [ ] **Step 3: Implement the minimal container/build changes**

Update `docker-entrypoint.sh`:

```sh
#!/bin/sh
set -eu

required_vars="TG_BOT_TOKEN TG_CHAT_ID SUBSCRIBE_PASSWORD"
DATA_DIR="${DATA_DIR:-/app/data}"

for var in $required_vars; do
    eval "value=\${$var:-}"
    if [ -z "$value" ]; then
        echo "[startup-check] Missing required environment variable: $var" >&2
        exit 1
    fi
done

mkdir -p "$DATA_DIR" "$DATA_DIR/tmp"

exec python main.py
```

Update `Dockerfile`:

```dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]
```

Update `docker-compose.yml`:

```yaml
services:
  ltt-strategy:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: ltt-strategy
    restart: unless-stopped
    env_file:
      - .env
    environment:
      TG_BOT_TOKEN: ${TG_BOT_TOKEN:-}
      TG_CHAT_ID: ${TG_CHAT_ID:-}
      SUBSCRIBE_PASSWORD: ${SUBSCRIBE_PASSWORD:-}
      LOGLEVEL: ${LOGLEVEL:-INFO}
      MAX_WORKERS: ${MAX_WORKERS:-8}
      DATA_DIR: /app/data
    volumes:
      - ./data:/app/data
```

Update `.dockerignore`:

```text
__pycache__/
*.pyc
*.pyo
*.pyd
*.log
*.sqlite3
.git/
.gitignore
.vscode/
.idea/
tmp/
data/
allowed_users.txt
user_settings.json
.env
venv/
.venv/
env/
ENV/
dist/
build/
*.egg-info/
```

Update `.env.example` with an explicit optional runtime directory note:

```dotenv
# Telegram Bot 配置（必填）
TG_BOT_TOKEN=1234567890:replace_with_real_bot_token
TG_CHAT_ID=replace_with_real_chat_id

# 用户订阅密码（必填）
SUBSCRIBE_PASSWORD=replace_with_real_password

# 运行参数（可选）
# LOGLEVEL 可选: DEBUG / INFO / WARNING / ERROR / CRITICAL
LOGLEVEL=INFO

# 并发线程数（正整数）
MAX_WORKERS=8

# 可选：运行时数据目录（ClawCloud / docker run / 本地 python 可使用）
# Compose 固定挂载到 /app/data，不建议在 Compose 中改 DATA_DIR
# 容器内默认 /app/data；本地直接执行 python main.py 时默认 ./data
# DATA_DIR=/app/data
```

- [ ] **Step 4: Run the tests and config validation**

Run: `python3 -m unittest discover -s tests -p 'test_deployment_files.py' -v && cp .env.example .env && bash -n docker-entrypoint.sh && docker compose config >/dev/null`
Expected: PASS for deployment-file tests, `.env` is prepared for Compose parsing, no shell syntax errors, and no Compose config errors.

- [ ] **Step 5: Prepare the checkpoint commit**

```bash
git add docker-entrypoint.sh Dockerfile docker-compose.yml .dockerignore .env.example tests/test_deployment_files.py
git commit -m "fix: align docker runtime bootstrap with data directory model"
```

Use this commit only if the user has asked you to create a commit at this checkpoint.

---

### Task 5: Update repository documentation to match the new runtime model

**Files:**
- Create: `tests/test_readme_docs.py`
- Modify: `README.md:43-167`

- [ ] **Step 1: Write the failing README regression test**

```python
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReadmeDocsTests(unittest.TestCase):
    def test_readme_mentions_clawcloud_compose_and_local_data_dir(self):
        text = (ROOT / 'README.md').read_text(encoding='utf-8')
        self.assertIn('ClawCloud', text)
        self.assertIn('/app/data', text)
        self.assertIn('./data', text)
        self.assertIn('worker / background service', text)
        self.assertNotIn('├── allowed_users.txt', text)
        self.assertNotIn('├── user_settings.json', text)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest discover -s tests -p 'test_readme_docs.py' -v`
Expected: FAIL because the current README still documents root-level runtime files and has no ClawCloud section.

- [ ] **Step 3: Implement the minimal doc rewrite**

Update the project structure block to use `data/` as the runtime directory:

```text
LTT_Strategy/
├── config.py
├── exchange_utils.py
├── main.py
├── strategy_sig.py
├── notifier.py
├── utils.py
├── requirements.txt
├── data/                   # 运行时目录（本地 / Compose 持久化）
│   ├── allowed_users.txt
│   ├── user_settings.json
│   ├── strategy.log
│   └── tmp/
└── README.md
```

Add a dedicated ClawCloud deployment section before the Compose section:

```markdown
### 2. ClawCloud Docker 部署

- 使用仓库中的 `Dockerfile` 构建镜像
- 在平台中配置：`TG_BOT_TOKEN`、`TG_CHAT_ID`、`SUBSCRIBE_PASSWORD`
- 可选配置：`LOGLEVEL`、`MAX_WORKERS`、`DATA_DIR`
- 将持久化目录挂载到 `/app/data`
- 该部署方式适用于不要求 HTTP 监听端口的 worker / background service
```

Rewrite the Compose section so it explains the unified runtime model:

```markdown
### 3. Docker Compose 部署

先复制示例环境变量文件：

```bash
cp .env.example .env
```

然后编辑 `.env` 并启动：

```bash
docker compose up -d --build
```

默认持久化目录为 `./data`，容器内对应 `/app/data`，其中包括：
- `allowed_users.txt`
- `user_settings.json`
- `strategy.log`
- `tmp/last_can_biao_xiu_state_*.txt`
```

Add a short local direct-run note:

```markdown
### 4. 本地直接运行 Python

未显式设置 `DATA_DIR` 时，本地 `python main.py` 默认把可变运行时文件写入 `./data`，而不是仓库根目录。
```

- [ ] **Step 4: Run the doc regression test**

Run: `python3 -m unittest discover -s tests -p 'test_readme_docs.py' -v`
Expected: PASS with 1 test, 0 failures.

- [ ] **Step 5: Prepare the checkpoint commit**

```bash
git add README.md tests/test_readme_docs.py
git commit -m "docs: document clawcloud and unified runtime directory"
```

Use this commit only if the user has asked you to create a commit at this checkpoint.

---

### Task 6: Run the full verification suite and hand off for execution

**Files:**
- Verify: `config.py`
- Verify: `utils.py`
- Verify: `main.py`
- Verify: `notifier.py`
- Verify: `strategy_sig.py`
- Verify: `docker-entrypoint.sh`
- Verify: `Dockerfile`
- Verify: `docker-compose.yml`
- Verify: `.dockerignore`
- Verify: `.env.example`
- Verify: `README.md`
- Verify: `tests/test_main_startup.py`
- Verify: `tests/test_notifier_runtime.py`
- Verify: `tests/test_runtime_config.py`
- Verify: `tests/test_runtime_state.py`
- Verify: `tests/test_deployment_files.py`
- Verify: `tests/test_readme_docs.py`

- [ ] **Step 1: Run the full unit-test suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS for startup-order, notifier-persistence, runtime-path, migration, deployment-file, and README tests.

- [ ] **Step 2: Run syntax and config verification**

Run: `cp .env.example .env && bash -n docker-entrypoint.sh && docker compose config >/dev/null && python3 -m py_compile config.py main.py notifier.py strategy_sig.py exchange_utils.py utils.py`
Expected: `.env` is prepared for Compose parsing, no shell syntax errors, no Compose config errors, and no `py_compile` output.

- [ ] **Step 3: Build the image**

Run: `docker build -t ltt-strategy:test .`
Expected: build completes successfully.

- [ ] **Step 4: Verify the fast-fail startup path**

Run: `docker run --rm ltt-strategy:test`
Expected: container exits non-zero with `[startup-check] Missing required environment variable: TG_BOT_TOKEN` (or the first missing required variable).

- [ ] **Step 5: Verify positive bootstrap and persistence behavior**

Run: `tmpdir=$(mktemp -d) && docker run --rm --entrypoint python -e TG_BOT_TOKEN=test-token -e TG_CHAT_ID=test-chat -e SUBSCRIBE_PASSWORD=test-password -v "$tmpdir:/app/data" ltt-strategy:test -c "import main; from strategy_sig import set_last_can_signal; main.monitor_new_users=lambda: None; main.set_bot_commands=lambda: None; main.send_telegram_message=lambda *args, **kwargs: None; main.job=lambda: set_last_can_signal('BTC', 'state-v1'); main.schedule.every=lambda *args, **kwargs: type('Every', (), {'minutes': type('Minutes', (), {'do': staticmethod(lambda fn: None)})()})(); main.threading.Thread=lambda *args, **kwargs: type('DummyThread', (), {'start': staticmethod(lambda: None)})(); main.main(run_loop=False)" && test -f "$tmpdir/allowed_users.txt" && test -f "$tmpdir/user_settings.json" && test -f "$tmpdir/strategy.log" && test -f "$tmpdir/tmp/last_can_biao_xiu_state_BTC.txt"`
Expected: command succeeds and the mounted host directory contains `allowed_users.txt`, `user_settings.json`, `strategy.log`, and `tmp/last_can_biao_xiu_state_BTC.txt` after the real `main.main(run_loop=False)` startup path runs.

- [ ] **Step 6: Verify existing persisted files are reused without overwrite**

Run: `tmpdir=$(mktemp -d) && printf 'keep-me\n' > "$tmpdir/allowed_users.txt" && printf '{"keep":true}' > "$tmpdir/user_settings.json" && printf 'keep-log' > "$tmpdir/strategy.log" && mkdir -p "$tmpdir/tmp" && printf 'keep-state' > "$tmpdir/tmp/last_can_biao_xiu_state_BTC.txt" && docker run --rm --entrypoint python -e TG_BOT_TOKEN=test-token -e TG_CHAT_ID=test-chat -e SUBSCRIBE_PASSWORD=test-password -v "$tmpdir:/app/data" ltt-strategy:test -c "from utils import prepare_runtime_state; from config import DATA_DIR, TMP_DIR, ALLOWED_USERS_FILE, USER_SETTINGS_FILE, LOG_FILE; prepare_runtime_state(data_dir=DATA_DIR, tmp_dir=TMP_DIR, allowed_users_file=ALLOWED_USERS_FILE, user_settings_file=USER_SETTINGS_FILE, log_file=LOG_FILE, legacy_allowed_users_file='allowed_users.txt', legacy_user_settings_file='user_settings.json', legacy_tmp_dir='tmp', legacy_log_file='strategy.log')" && test "$(cat "$tmpdir/allowed_users.txt")" = 'keep-me' && test "$(cat "$tmpdir/user_settings.json")" = '{"keep":true}' && test "$(cat "$tmpdir/strategy.log")" = 'keep-log' && test "$(cat "$tmpdir/tmp/last_can_biao_xiu_state_BTC.txt")" = 'keep-state'`
Expected: command succeeds and all seeded files remain unchanged after bootstrap-only reuse verification.

- [ ] **Step 7: Verify application writes land in the persisted runtime directory**

Run: `tmpdir=$(mktemp -d) && docker run --rm --entrypoint python -e TG_BOT_TOKEN=test-token -e TG_CHAT_ID=test-chat -e SUBSCRIBE_PASSWORD=test-password -v "$tmpdir:/app/data" ltt-strategy:test -c "from utils import prepare_runtime_state; from config import DATA_DIR, TMP_DIR, ALLOWED_USERS_FILE, USER_SETTINGS_FILE, LOG_FILE; from strategy_sig import set_last_can_signal; prepare_runtime_state(data_dir=DATA_DIR, tmp_dir=TMP_DIR, allowed_users_file=ALLOWED_USERS_FILE, user_settings_file=USER_SETTINGS_FILE, log_file=LOG_FILE, legacy_allowed_users_file='allowed_users.txt', legacy_user_settings_file='user_settings.json', legacy_tmp_dir='tmp', legacy_log_file='strategy.log'); open(LOG_FILE, 'a', encoding='utf-8').write('boot-log\n'); set_last_can_signal('BTC', 'state-v1')" && test "$(cat "$tmpdir/strategy.log")" = 'boot-log' && test "$(cat "$tmpdir/tmp/last_can_biao_xiu_state_BTC.txt")" = 'state-v1'`
Expected: command succeeds and runtime writes land inside the mounted persistence directory.

- [ ] **Step 8: Prepare the final checkpoint commit**

```bash
git add config.py utils.py main.py notifier.py strategy_sig.py docker-entrypoint.sh Dockerfile docker-compose.yml .dockerignore .env.example README.md tests
git commit -m "feat: unify runtime data paths for clawcloud deployment"
```

Use this commit only if the user has asked you to create a commit at this checkpoint.
