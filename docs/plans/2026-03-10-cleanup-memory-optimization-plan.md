# 项目清理与内存优化 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在不改变项目功能和对外行为的前提下，做一次保守的代码清理与内存优化，删除明确未使用代码，缩短不必要对象生命周期，并保持代码整洁。

**Architecture:** 优化严格限定在现有单进程轮询 + 并发抓数 + Telegram 推送架构内，不改变主流程与策略逻辑。重点收紧 `main.py` 中的数据生命周期，删除 `exchange_utils.py` / `notifier.py` 中明确未使用的代码路径，并仅对等价实现做微调。

**Tech Stack:** Python 3, pandas, numpy, ccxt, requests, yfinance, schedule

---

### Task 1: 删除 `main.py` 中未使用的 DataFrame 缓存

**Files:**
- Modify: `main.py:31-80`
- Verify: `main.py:33-55`

**Step 1: 确认缓存未被消费**

检查 `main.py` 中 `df_cache = {}` 与 `df_cache[(symbol_short, timeframe)] = df` 的唯一引用。

Expected: 仅有赋值，没有任何读取逻辑。

**Step 2: 删除未使用缓存**

从 `job()` 中删除：

```python
df_cache = {}
...
df_cache[(symbol_short, timeframe)] = df
```

保留后续信号处理逻辑不变。

**Step 3: 复查对象生命周期**

确认删除后，每个 `df` 仅在单次 future 结果处理分支内使用，不再被额外容器长期引用。

Expected: `df` 在处理完当前 symbol/timeframe 后可被释放。

**Step 4: 语法级检查**

Run: `python -m py_compile main.py`
Expected: 无输出，表示编译通过。

---

### Task 2: 删除 `exchange_utils.py` 中明确未使用的函数与无效参数

**Files:**
- Modify: `exchange_utils.py:35-73`
- Modify: `exchange_utils.py:132-139`
- Verify: `exchange_utils.py` 全文件调用关系

**Step 1: 确认 `get_yahoo_data()` 未被调用**

检查仓库内 `get_yahoo_data(` 的引用。

Expected: 只有函数定义，没有调用。

**Step 2: 删除未使用函数**

删除整个函数：

```python
def get_yahoo_data(symbol, limit=500):
    ...
```

因为实际 Yahoo 路径使用的是 `get_turtle_data()`。

**Step 3: 删除 `get_data()` 的无效参数**

当前定义：

```python
def get_data(symbol, timeframe, limit=500, retry=2):
```

将其改为：

```python
def get_data(symbol, timeframe, limit=500):
```

因为 `retry` 参数未被使用，也未在调用方传入。

**Step 4: 语法级检查**

Run: `python -m py_compile exchange_utils.py`
Expected: 无输出，表示编译通过。

---

### Task 3: 删除 `notifier.py` 中明确未使用的串行发送备用函数

**Files:**
- Modify: `notifier.py:391-395`
- Verify: `notifier.py` / 全仓库调用关系

**Step 1: 确认 `send_to_allowed_users_serial()` 未被调用**

检查 `send_to_allowed_users_serial(` 的仓库引用。

Expected: 只有函数定义，没有调用。

**Step 2: 删除未使用函数**

删除：

```python
def send_to_allowed_users_serial(msg):
    users = load_allowed_users()
    for user_id in users:
        send_message(user_id, msg)
```

**Step 3: 语法级检查**

Run: `python -m py_compile notifier.py`
Expected: 无输出，表示编译通过。

---

### Task 4: 收紧 `notifier.py` 中并发发送的包装层

**Files:**
- Modify: `notifier.py:295-296`
- Modify: `notifier.py:312-317`
- Modify: `notifier.py:429-433`

**Step 1: 确认 `send_message_async()` 只是透传包装**

当前实现：

```python
def send_message_async(chat_id, text):
    return send_message(chat_id, text)
```

Expected: 没有额外逻辑，仅增加一层调用。

**Step 2: 内联到线程池提交点**

将：

```python
executor.submit(send_message_async, user_id, msg)
```

改为：

```python
executor.submit(send_message, user_id, msg)
```

然后删除 `send_message_async()` 定义。

**Step 3: 复查两处并发发送路径**

检查：
- `send_to_allowed_users()`
- `send_to_target_users_concurrent()`

Expected: 都直接调用 `send_message`，行为保持等价，仅少一层函数栈与符号噪音。

**Step 4: 语法级检查**

Run: `python -m py_compile notifier.py`
Expected: 无输出，表示编译通过。

---

### Task 5: 对 `main.py` 做等价级的小幅内存收紧

**Files:**
- Modify: `main.py:47-79`

**Step 1: 审查每个 future 分支中的中间对象**

重点关注：
- `signals`
- `turtle_signals`
- `can_biao_xiu_signals`
- `symbol_short`

识别哪些对象只需在局部最短作用域内存在。

**Step 2: 做等价级收紧**

允许的改动示例：
- 删除不必要的中间列表保存，如果可以保持为“立即消费后结束作用域”
- 避免无意义变量保留到更长分支后段

禁止：
- 合并业务逻辑
- 改变信号执行顺序
- 改变异常处理边界

**Step 3: 复查可读性**

Expected: 代码仍然清晰，不能为了省一个局部变量而让逻辑更难读。

**Step 4: 语法级检查**

Run: `python -m py_compile main.py`
Expected: 无输出，表示编译通过。

---

### Task 6: 全局静态复核并整理变更说明

**Files:**
- Verify: `main.py`
- Verify: `exchange_utils.py`
- Verify: `notifier.py`
- Optional note update: `docs/plans/2026-03-10-cleanup-memory-optimization-design.md`

**Step 1: 全仓库复查删除项引用**

检查以下标识符是否已无残留错误引用：
- `df_cache`
- `get_yahoo_data`
- `send_to_allowed_users_serial`
- `send_message_async`
- `retry`（仅 `get_data` 旧签名中的无效参数）

Expected: 没有残留错误引用。

**Step 2: 运行最小语法检查**

Run: `python -m py_compile main.py exchange_utils.py notifier.py strategy_sig.py utils.py config.py`
Expected: 无输出，表示全部编译通过。

**Step 3: 产出变更摘要**

总结每项修改：
- 删除了什么
- 为什么确认未使用
- 为什么属于低风险
- 对内存或整洁度的具体帮助是什么

**Step 4: 准备提交（仅在用户要求时）**

如果用户要求提交，再执行：

```bash
git add main.py exchange_utils.py notifier.py docs/plans/2026-03-10-cleanup-memory-optimization-design.md
git commit -m "refactor: trim unused code and reduce transient memory retention"
```
