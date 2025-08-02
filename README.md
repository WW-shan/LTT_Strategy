# LTT_Strategy

一个基于 Python 的加密货币交易策略自动化系统，支持多周期 K 线数据获取、技术指标计算、信号检测及 Telegram 推送通知。集成 Yahoo Finance 数据源，提供更丰富的历史数据支持。

---

## 项目简介

LTT_Strategy 是一个先进的加密货币交易信号监控系统，通过多种技术指标和自定义策略（海龟交易法、RSI 极值、参标修信号等）自动监控加密货币市场。系统采用双数据源架构（Bitget + Yahoo Finance），实时生成高质量交易信号，并通过智能 Telegram 机器人推送给授权用户，帮助交易者及时把握市场机会。

---

## 功能特点

### 📊 数据源

- **Bitget 交易所**：实时 USDT 永续合约数据获取
- **Yahoo Finance**：海龟交易法和参标修专用历史数据（500 根 K 线）
- **多周期支持**：1 小时、4 小时、1 天 K 线数据分析

### 🔧 技术指标

- **均线系统**：MA5、MA10、MA20、MA200
- **RSI 指标**：6 周期 RSI 极值检测
- **唐奇安通道**：28 周期 DC 通道突破
- **数值精度**：所有价格数据精确到 6 位小数

### 📈 交易信号

- **海龟交易法**：基于 DC 中轨与 MA200 交叉的买卖信号
- **参标修信号**：高级突破策略，支持参-标-修三阶段识别
- **RSI6 极值**：超买超卖信号（>95 或<5）
- **五连阴**：连续下跌预警信号（仅 BTC、ETH）

### 🤖 Telegram 机器人

- **智能推送**：个性化信号推送，支持周期和信号类型过滤
- **用户管理**：订阅密码验证、自动清理被屏蔽用户
- **管理员功能**：用户管理、批量推送、置顶消息
- **并发发送**：多线程消息推送，支持大量用户

---

## 项目结构

```
LTT_Strategy/
├── config.py              # 核心配置文件，API密钥、参数设置
├── exchange_utils.py      # 双数据源接口（Bitget + Yahoo Finance）
├── main.py                # 主程序，任务调度和信号处理
├── strategy_sig.py        # 信号检测逻辑（海龟、参标修、RSI等）
├── notifier.py            # Telegram机器人和用户管理系统
├── utils.py               # 工具函数
├── requirements.txt       # Python依赖包列表
├── allowed_users.txt      # 授权用户列表（自动管理）
├── user_settings.json     # 用户个性化设置
├── tmp/                   # 信号缓存和临时文件
└── README.md              # 项目文档
```

---

## 环境依赖

- **Python 3.8 及以上**
- **核心依赖库**：

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

### 1. 环境变量配置（推荐）

```bash
export TG_BOT_TOKEN="your_telegram_bot_token"
export TG_CHAT_ID="your_telegram_chat_id"
export SUBSCRIBE_PASSWORD="your_subscription_password"
```

### 2. 配置文件说明

- **交易所 API**：Bitget API 密钥配置
- **Telegram 设置**：Bot Token、管理员 Chat ID、订阅密码
- **策略参数**：DC 周期、均线周期、检测频率等
- **用户设置**：支持个性化信号类型和时间周期过滤

---

## 使用方法

### 1. 快速开始

```bash
# 克隆项目
git clone https://github.com/WW-shan/LTT_Strategy.git
cd LTT_Strategy

# 安装依赖
pip install -r requirements.txt

# 配置环境变量（或编辑config.py）
# 运行系统
python main.py
```

### 2. Telegram 机器人命令

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

### 3. 用户订阅流程

1. 用户向机器人发送任意消息
2. 机器人要求输入订阅密码
3. 输入正确密码后自动订阅
4. 使用`/settings`查看和修改推送设置

---

## 技术架构

```
┌─────────────────┐    ┌─────────────────┐
│   Bitget API    │    │ Yahoo Finance   │
│   (实时数据)     │    │   (历史数据)      │
└─────────┬───────┘    └─────────┬───────┘
          │                      │
          └─────────┬────────────┘
                    │
         ┌─────────────────────┐
         │   Strategy Engine   │
         │    (信号检测引擎)     │
         └─────────┬───────────┘
                   │
         ┌─────────────────────┐
         │  Telegram Bot API   │
         │    (消息推送系统)     │
         └─────────────────────┘
```

---

## 贡献指南

欢迎提交 Issue 或 Pull Request：

1. **Bug 报告**：请提供详细的错误信息和复现步骤
2. **功能建议**：描述新功能的用途和实现思路
3. **代码贡献**：遵循项目代码规范，添加适当的测试和文档

---

## 许可证

本项目采用 MIT 许可证，详见 LICENSE 文件。

---

## 联系方式

如有问题或建议，请通过以下方式联系：

- GitHub Issues
