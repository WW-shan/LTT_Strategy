# LTT_Strategy

一个基于 Python 的加密货币交易策略自动化系统，支持多周期 K 线数据获取、技术指标计算、信号检测及 Telegram 推送通知。系统集成 Bitget 与 Yahoo Finance 双数据源，适合以常驻 worker / background service 模式持续运行。

---

## 项目简介

LTT_Strategy 是一个面向 Telegram 推送场景的交易信号监控系统，通过海龟交易法、RSI 极值、参标修、五连阴等策略自动扫描市场，并把结果推送给授权用户。程序启动后会初始化运行时数据目录、执行一次策略扫描，然后按固定周期持续运行。

---

## 功能特点

### 数据源

- Bitget 交易所：实时 USDT 永续合约数据获取
- Yahoo Finance：海龟交易法和参标修专用历史数据（500 根 K 线）
- 多周期支持：1 小时、4 小时、1 天 K 线数据分析

### 技术指标

- 均线系统：MA5、MA10、MA20、MA200
- RSI 指标：6 周期 RSI 极值检测
- 唐奇安通道：28 周期 DC 通道突破
- 数值精度：所有价格数据精确到 6 位小数

### 交易信号

- 海龟交易法：基于 DC 中轨与 MA200 交叉的买卖信号
- 参标修信号：高级突破策略，支持参-标-修三阶段识别
- RSI6 极值：超买超卖信号（>95 或 <5）
- 五连阴：连续下跌预警信号（仅 BTC、ETH）

### Telegram 机器人

- 智能推送：个性化信号推送，支持周期和信号类型过滤
- 用户管理：订阅密码验证、自动清理被屏蔽用户
- 管理员功能：用户管理、批量推送、置顶消息
- 并发发送：多线程消息推送，支持大量用户

---

## 项目结构

```text
LTT_Strategy/
├── config.py              # 核心配置文件，环境变量与默认参数
├── exchange_utils.py      # 双数据源接口（Bitget + Yahoo Finance）
├── main.py                # 主程序，任务调度和信号处理
├── strategy_sig.py        # 信号检测逻辑（海龟、参标修、RSI 等）
├── notifier.py            # Telegram 机器人和用户管理系统
├── utils.py               # 运行时目录与文件初始化工具
├── requirements.txt       # Python 依赖列表
├── tests/                 # unittest 回归测试
├── data/                  # 默认运行时数据目录
│   ├── allowed_users.txt  # 订阅用户列表
│   ├── user_settings.json # 用户个性化推送配置
│   ├── strategy.log       # 运行日志
│   └── tmp/               # 临时状态目录
│       └── last_can_biao_xiu_state_<SYMBOL>.txt
└── README.md              # 项目文档
```

说明：
- 本地直接运行时，若未设置 `DATA_DIR`，默认使用仓库内的 `./data`。
- Docker / ClawCloud 容器内建议把持久化目录挂载到 `/app/data`。
- 默认情况下，运行时文件位于 `data/` 下，而不是项目根目录。
- 为兼容旧版本升级，启动时会把项目根目录下遗留的 `user_settings.json` 一次性迁移到 `data/user_settings.json`（仅在目标文件不存在时执行）。
- 迁移完成后，程序始终以数据目录中的 `user_settings.json` 为准；如果显式设置了 `DATA_DIR`，则使用对应数据目录中的文件。

---

## 环境依赖

- Python 3.8 及以上
- 核心依赖安装命令：

```bash
pip install -r requirements.txt
```

主要依赖：

- `ccxt>=4.4.98` - 交易所数据接口
- `pandas>=2.3.1` - 数据处理和分析
- `yfinance>=0.2.65` - Yahoo Finance 数据源
- `requests>=2.32.3` - HTTP 请求处理
- `schedule>=1.2.2` - 任务调度
- `numpy>=1.26.4` - 数值计算

---

## 配置说明

### 必需环境变量

```bash
export TG_BOT_TOKEN="your_telegram_bot_token"
export TG_CHAT_ID="your_telegram_chat_id"
export SUBSCRIBE_PASSWORD="your_subscription_password"
```

### 可选环境变量

```bash
export LOGLEVEL="INFO"
export MAX_WORKERS="8"
# export DATA_DIR="/absolute/path/to/data"
```

说明：
- `TG_BOT_TOKEN`、`TG_CHAT_ID`、`SUBSCRIBE_PASSWORD` 为必填项。
- `DATA_DIR` 用于覆盖默认运行时目录。
- 在容器部署中，推荐把持久化挂载目标固定为 `/app/data`，并让 `DATA_DIR=/app/data`。

---

## 使用方法

### 1. 本地直接运行

```bash
# 克隆项目
git clone https://github.com/WW-shan/LTT_Strategy.git
cd LTT_Strategy

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
export TG_BOT_TOKEN="your_telegram_bot_token"
export TG_CHAT_ID="your_telegram_chat_id"
export SUBSCRIBE_PASSWORD="your_subscription_password"

# 运行系统
python main.py
```

补充说明：
- 本地直接运行时，如果没有设置 `DATA_DIR`，程序默认会把运行时文件写入仓库下的 `./data`，而不是项目根目录。
- 兼容旧版本升级时，启动阶段会把项目根目录下遗留的 `./user_settings.json` 一次性迁移到 `./data/user_settings.json`（仅在目标文件不存在时执行）；迁移完成后，程序始终读取 `./data/user_settings.json`。
- 如果你希望把运行时状态放到其他位置，可以显式设置 `DATA_DIR`。

### 2. ClawCloud Docker 部署

适用于把程序作为常驻 worker / background service 运行的场景。该项目不提供 HTTP listener，也不需要暴露 Web 端口。

部署要点：
- 在 ClawCloud 中配置以下必需环境变量：
  - `TG_BOT_TOKEN`
  - `TG_CHAT_ID`
  - `SUBSCRIBE_PASSWORD`
- 可按需配置：
  - `LOGLEVEL`
  - `MAX_WORKERS`
  - `DATA_DIR=/app/data`
- 为容器添加持久化存储，并把挂载目标设置为 `/app/data`。

容器内建议的持久化目录结构：

```text
/app/data/
├── allowed_users.txt
├── user_settings.json
├── strategy.log
└── tmp/
```

说明：
- `/app/data` 是容器内统一的运行时目录。
- 订阅用户、用户设置、日志和去重临时状态都应保存在这个持久化目录中。
- 容器启动后会直接运行 `python main.py`，适合作为后台持续运行服务。

### 3. Docker Compose 部署

先复制示例环境变量文件：

```bash
cp .env.example .env
```

Windows PowerShell 可使用：

```powershell
Copy-Item .env.example .env
```

然后编辑 `.env` 填入真实值：

```bash
TG_BOT_TOKEN=your_telegram_bot_token
TG_CHAT_ID=your_telegram_chat_id
SUBSCRIBE_PASSWORD=your_subscription_password
LOGLEVEL=INFO
MAX_WORKERS=8
```

当前 `docker-compose.yml` 已固定采用以下映射：

```text
./data -> /app/data
```

这意味着：
- 宿主机上的 `./data` 会持久化容器内 `/app/data` 的全部运行时文件。
- 持久化内容包括：
  - `allowed_users.txt`
  - `user_settings.json`
  - `strategy.log`
  - `tmp/`
- Compose 模式下不需要在 `.env` 中再设置 `DATA_DIR`，因为服务已经固定使用 `/app/data`。
- 该服务同样以 worker / background service 模式运行，不提供 HTTP 监听端口。

一键启动：

```bash
docker compose up -d --build
```

查看日志：

```bash
docker compose logs -f
```

停止服务：

```bash
docker compose down
```

### 4. Telegram 机器人命令

#### 普通用户命令

- `/settings` - 查看当前推送设置
- `/set_timeframes 1h,4h,1d` - 设置接收的时间周期
- `/set_signals turtle_buy,turtle_sell,can_biao_xiu` - 设置信号类型
- `/unsubscribe` - 退订推送

#### 管理员命令

- `/adduser <user_id>` - 手动添加用户
- `/removeuser <user_id>` - 移除用户
- `/listusers` - 查看所有订阅用户
- `/cleanblocked` - 清理被屏蔽的用户
- `/pin <消息内容>` - 发送置顶消息给所有用户

### 5. 用户订阅流程

1. 用户向机器人发送任意消息
2. 机器人要求输入订阅密码
3. 输入正确密码后自动订阅
4. 使用 `/settings` 查看和修改推送设置

---

## 技术架构

```text
┌─────────────────┐    ┌─────────────────┐
│   Bitget API    │    │ Yahoo Finance   │
│   (实时数据)     │    │   (历史数据)     │
└─────────┬───────┘    └─────────┬───────┘
          │                      │
          └─────────┬────────────┘
                    │
         ┌─────────────────────┐
         │   Strategy Engine   │
         │    (信号检测引擎)    │
         └─────────┬───────────┘
                   │
         ┌─────────────────────┐
         │  Telegram Bot API   │
         │    (消息推送系统)    │
         └─────────────────────┘
```

---

## 贡献指南

欢迎提交 Issue 或 Pull Request：

1. Bug 报告：请提供详细的错误信息和复现步骤
2. 功能建议：描述新功能的用途和实现思路
3. 代码贡献：遵循项目代码规范，添加适当的测试和文档

---

## 许可证

本项目采用 MIT 许可证，详见 `LICENSE` 文件。

---

## 联系方式

如有问题或建议，请通过 GitHub Issues 联系。
