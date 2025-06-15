# LTT_Strategy

一个基于Python的加密货币交易策略自动化系统，支持多周期K线数据获取、技术指标计算、信号检测及Telegram推送通知。

---

## 项目简介

LTT_Strategy旨在通过技术指标和自定义信号（如海龟交易法、RSI极值、参标修信号等）自动监控加密货币市场，实时生成买卖信号并通过Telegram机器人推送给授权用户，帮助交易者及时把握市场机会。

---

## 功能特点

- 支持Bitget交易所的USDT永续合约数据获取
- 多周期（1小时、4小时、1天）K线数据分析
- 多种技术指标计算（均线、RSI、唐奇安通道等）
- 多种交易信号检测（海龟交易法买卖信号、RSI极值、五连阴、参标修信号）
- Telegram机器人推送信号，支持用户订阅和退订
- 多线程并发数据获取，提高效率
- 日志记录和异常处理，保证稳定运行

---

## 项目结构

```
Strategy/
├── config.py              # 配置文件，包含API密钥、参数设置等
├── exchange_utils.py      # 交易所数据接口封装，获取K线数据等
├── main.py                # 主程序，调度任务、信号处理和推送
├── notifier.py            # Telegram消息推送和用户管理
├── signal.py              # 技术指标计算及信号检测逻辑
├── allowed_users.txt      # 授权用户ID列表（自动管理）
├── tmp/                   # 缓存和日志文件夹
└── README.md              # 项目说明文档
```


---

## 环境依赖

- Python 3.7及以上
- 依赖库（可通过`requirements.txt`安装）：
    - ccxt
    - pandas
    - numpy
    - schedule
    - requests

安装依赖示例：

```bash
pip install -r requirements.txt
```


---

## 配置说明

1. **API密钥**
在`config.py`中配置你的Bitget API Key和Secret，以及Telegram Bot Token和Chat ID，支持通过环境变量覆盖。
2. **参数调整**
可修改配置文件中的交易对、时间周期、技术指标参数等，以适应不同策略需求。
3. **订阅密码**
Telegram推送支持订阅密码机制，防止未授权用户接收消息。

---

## 使用方法

1. 克隆仓库并进入项目目录：
```bash
git clone git@github.com:WW-shan/LTT_Strategy.git
cd LTT_Strategy
```

2. 安装依赖：
```bash
pip install -r requirements.txt
```

3. 配置环境变量或直接编辑`config.py`，填写API密钥和Telegram相关信息。
4. 运行主程序：
```bash
python main.py
```

程序将定时获取数据，检测信号，并通过Telegram推送给授权用户。

---

## 订阅管理

- 新用户需通过Telegram发送订阅密码进行授权
- 管理员可通过Telegram命令手动添加或移除用户
- 用户可通过`/unsubscribe`命令退订推送

---

## 日志和调试

- 日志文件保存在`tmp/strategy.log`
- 可通过修改`config.py`中的`LOGLEVEL`调整日志级别（DEBUG/INFO/WARNING/ERROR）

---

## 未来计划

- 支持更多交易所和交易对
- 增加更多策略信号和回测功能
- 优化推送消息格式和用户交互体验
- 支持Web界面管理和展示

---

## 贡献与反馈

欢迎提交Issue或Pull Request，提出建议或贡献代码。
