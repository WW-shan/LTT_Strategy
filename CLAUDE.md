# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### 本地安装
```bash
pip install -r requirements.txt
```

必需环境变量：

```bash
export TG_BOT_TOKEN="your_telegram_bot_token"
export TG_CHAT_ID="your_telegram_chat_id"
export SUBSCRIBE_PASSWORD="your_subscription_password"
```

### 本地运行
```bash
python main.py
```

### Docker
```bash
cp .env.example .env
docker compose up -d --build
docker compose logs -f
docker compose down
```

注意：当前 `docker-compose.yml` 没有挂载 volume，`allowed_users.txt`、`user_settings.json`、`tmp/`、`strategy.log` 等运行时文件在容器重建后会丢失。

### 测试与代码检查
- 当前仓库没有配置测试套件、linter 或 formatter。
- 因为尚未接入测试框架，所以目前也没有“运行单个测试”的命令。

## Architecture

### 运行流程
- `main.py` 是主入口。它会初始化运行时目录和文件，启动 Telegram 用户监听线程，注册机器人命令，每 60 分钟调度一次策略任务，启动时会先立即执行一次，然后进入常驻循环。
- 每次调度执行时，会先预热 Bitget 连接，获取所有活跃的 USDT 永续合约交易对，并发拉取市场数据，执行信号检测，再把结果交给通知层处理。

### 主要模块
- `config.py`：集中管理环境变量配置和默认参数，例如时间周期、唐奇安通道参数、均线参数、默认用户偏好等。
- `exchange_utils.py`：数据访问层。普通行情通过 `ccxt` 从 Bitget 获取；海龟策略和参标修相关路径通过 `yfinance` 从 Yahoo Finance 获取。
- `strategy_sig.py`：指标计算与信号识别，包括 RSI6 极值、海龟买卖、参标修、五连阴。
- `notifier.py`：Telegram 集成、订阅用户管理、按用户偏好过滤信号、管理员命令、被屏蔽用户清理、并发消息发送。
- `utils.py`：启动阶段使用的文件 / 目录初始化工具。

### 关键数据源划分
- 普通扫描数据来自 Bitget。
- 海龟策略和参标修使用 Yahoo Finance 数据，而不是 `main.py` 中已经拉取的 Bitget 数据。
- 对于 `4h` 海龟数据，实际是先取 Yahoo 的 `1h` 数据再重采样成 `4h`。

### 运行时状态文件
- `allowed_users.txt`：订阅用户 ID 列表。
- `user_settings.json`：用户个性化推送配置。
- `tmp/last_can_biao_xiu_state_<SYMBOL>.txt`：参标修信号去重状态，避免重复推送。
- `strategy.log`：运行日志。

## Gotchas

- `rsi6_extreme` 的处理路径与普通可选信号不同，基本可以视为始终启用。
- `main.py` 会先获取一轮 Bitget 数据，但海龟策略和参标修在 `strategy_sig.py` 中仍会再次请求 Yahoo Finance。
- `config.py` 中的 `SYMBOLS` 控制额外信号（如 `five_down`）；当前默认只包含 `BTC/USDT:USDT`。
- `.gitignore` 会忽略所有 `*.txt` 和 `*.json` 文件，以及 `tmp/`、`.env`、日志文件。这不只是运行时文件问题；未来如果新增这两类文件，默认也不会出现在 `git status` 中。
