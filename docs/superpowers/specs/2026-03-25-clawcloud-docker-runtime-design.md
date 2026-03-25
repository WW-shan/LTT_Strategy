# 2026-03-25 ClawCloud Docker 部署与运行时目录统一设计

## 目标

在不改变项目核心业务行为的前提下，完成一套同时适用于 **ClawCloud 单 Docker 部署** 和 **本地 / VPS Docker Compose 部署** 的运行时与配置设计，确保：

- ClawCloud 不依赖 `docker compose` 也能直接部署
- 容器重建后用户订阅数据和用户设置不会丢失
- 本地 `docker compose` 体验继续保留
- 运行时状态目录边界清晰，不再依赖软链接兜底
- 镜像构建不会把本地 `.env` 或运行时数据打包进去

## 用户确认的约束

- 云平台为 **ClawCloud**
- ClawCloud **只兼容 Docker，不需要兼容 Compose**
- `allowed_users`、`user_settings` 等运行时用户数据 **必须持久化**
- 本次改造目标是 **既支持 ClawCloud 单 Docker 部署，也保留本地 / 服务器上的 docker compose 体验**

## 当前现状

### 已有能力

- 项目已经有 `Dockerfile`
- 项目已经有 `docker-compose.yml`
- 项目已经有启动前环境变量校验脚本 `docker-entrypoint.sh`
- Compose 当前已经挂载 `./data:/app/data`
- `.env.example` 已提供基础环境变量模板

### 当前缺口

1. **运行时文件路径仍然分散在项目根目录和 `tmp/` 中**
   - `main.py` 仍写入 `strategy.log`
   - `main.py` 仍初始化 `tmp`、`allowed_users.txt`
   - `notifier.py` 仍直接使用 `allowed_users.txt`
   - `strategy_sig.py` 仍直接写 `tmp/last_can_biao_xiu_state_*.txt`

2. **当前容器依赖入口脚本创建软链接来适配数据目录**
   - 这能工作，但不是稳定的运行时边界
   - 一旦代码里新增新的落盘点，容易再次绕开 `/app/data`

3. **`.dockerignore` 未排除 `.env` 和 `data/`**
   - 当前 `Dockerfile` 使用 `COPY . .`
   - 虽然 `.gitignore` 已忽略 `.env`，但 Docker 构建上下文是否包含文件由 `.dockerignore` 决定
   - 由于当前 `.dockerignore` 未排除 `.env` 和 `data/`，这些本地文件仍可能进入构建上下文并被复制进镜像
   - 这既有 secrets 风险，也会污染镜像内容

4. **README 仍主要围绕 Compose，一体化部署说明不足**
   - ClawCloud 的单 Docker 部署路径尚未明确
   - 数据持久化目录约束尚未完整说明

## 方案对比

### 方案 A：保持现状，继续依赖入口脚本软链接

**做法：**
- 保持 Python 代码中的现有路径写法不变
- 继续依赖 `docker-entrypoint.sh` 软链接 `/app/data/...` 到项目根目录

**优点：**
- 代码改动最小
- 短期可用

**缺点：**
- 运行时边界仍不清晰
- 新增落盘文件时容易再次绕开持久化目录
- 长期维护成本高

### 方案 B：统一运行时目录到 `/app/data`（采用）

**做法：**
- 通过配置统一所有运行时可变文件路径
- Python 代码直接读写 `/app/data` 体系，而不是项目根目录
- Docker 与 Compose 共用同一套运行时目录规范

**优点：**
- 底层逻辑清晰，状态边界稳定
- ClawCloud 与 Compose 行为一致
- 后续扩展时不容易出现状态漂移

**缺点：**
- 需要修改若干 Python 文件中的路径常量

### 方案 C：为 ClawCloud 维护单独部署分支

**做法：**
- 本地 / Compose 和 ClawCloud 分别维护两套部署配置

**优点：**
- 短期隔离感强

**缺点：**
- 双轨维护
- 小项目不值得承担长期分叉成本

## 采用方案

采用 **方案 B：统一运行时目录到 `/app/data`**。

底层逻辑如下：

- **云上部署入口以 Dockerfile 为准**，因为 ClawCloud 不依赖 Compose
- **本地 / VPS 保留 Compose**，但它只是另一种启动入口，不应该改变应用运行时行为
- **所有需要跨容器重建保留的数据必须收敛到一个明确目录**，否则“持久化”只是表面可用

## 设计

### 1. 部署架构

#### ClawCloud

- 使用仓库中的 `Dockerfile` 构建单容器镜像
- 在平台中配置环境变量：
  - `TG_BOT_TOKEN`
  - `TG_CHAT_ID`
  - `SUBSCRIBE_PASSWORD`
  - 可选：`LOGLEVEL`、`MAX_WORKERS`
- 将平台持久化目录挂载到 **`/app/data`**
- 不依赖 `docker compose`
- 部署前提：ClawCloud 需支持 **worker / background container** 这类不要求 HTTP 监听端口的运行模式；如果平台只支持 web service 并强制要求端口健康检查，则本方案需要额外健康检查设计后才能落地

#### 本地 / VPS

- 保留 `docker-compose.yml`
- 继续通过 `./data:/app/data` 挂载本地数据目录
- 与 ClawCloud 共享相同的应用路径语义和运行时目录约定

### 2. 运行时目录模型

统一定义以下运行时目录和文件：

- `DATA_DIR=/app/data`
- `TMP_DIR=/app/data/tmp`
- `ALLOWED_USERS_FILE=/app/data/allowed_users.txt`
- `USER_SETTINGS_FILE=/app/data/user_settings.json`
- `LOG_FILE=/app/data/strategy.log`

说明：

- 以上路径应通过配置统一导出，而不是在业务代码中写死字符串
- ClawCloud 与 Compose 容器内默认使用 `/app/data` 体系
- 本地直接运行 `python main.py` 时，默认运行时目录应为仓库下的 `./data`，避免继续把可变文件写回项目根目录

### 3. Python 代码改造范围

#### `config.py`

新增并统一导出：

- `DATA_DIR`
- `TMP_DIR`
- `ALLOWED_USERS_FILE`
- `USER_SETTINGS_FILE`
- `LOG_FILE`

要求：

- 所有运行时路径都从 `config.py` 读取
- 不再在其他模块中硬编码 `allowed_users.txt`、`tmp/...`、`strategy.log`

#### `main.py`

调整为：

- 日志写入 `LOG_FILE`
- 初始化目录时使用 `TMP_DIR`
- 初始化文件时使用 `ALLOWED_USERS_FILE`、`USER_SETTINGS_FILE`

#### `notifier.py`

调整为：

- 使用 `ALLOWED_USERS_FILE` 替代模块内硬编码的 `USER_FILE = "allowed_users.txt"`
- 保持原有读写逻辑不变，仅统一落盘路径

#### `strategy_sig.py`

调整为：

- 将参标修信号状态文件写入 `TMP_DIR`
- 不再硬编码 `tmp/last_can_biao_xiu_state_*.txt`

### 4. 容器启动策略

保留 `docker-entrypoint.sh`，但其职责收敛为：

1. 校验必填环境变量
2. 创建运行时目录与初始文件
3. 在升级场景下优先复用已存在的持久化文件
4. 启动 `python main.py`

具体要求：

- 校验：
  - `TG_BOT_TOKEN`
  - `TG_CHAT_ID`
  - `SUBSCRIBE_PASSWORD`
- 创建：
  - `/app/data`
  - `/app/data/tmp`
  - `/app/data/allowed_users.txt`
  - `/app/data/user_settings.json`
- 升级兼容：
  - 如果挂载目录中已经存在 `/app/data/allowed_users.txt` 或 `/app/data/user_settings.json`，新版本必须直接复用，不能覆盖
  - 如果升级时项目根目录仍残留旧路径文件，而 `/app/data` 中还没有对应文件，需要执行一次性迁移或临时兼容读取，保证已有用户数据不丢失
  - 迁移目标仅限已有运行时文件，不新增额外状态复制逻辑
- **不再依赖软链接来驱动应用路径兼容**；即使保留软链接兼容过渡，也应以代码直接使用 `/app/data` 路径为主

### 5. Dockerfile 设计

`Dockerfile` 需要继续满足 ClawCloud 单 Docker 部署。

建议保持：

- Python 3.11 slim 基础镜像
- 安装依赖
- 复制项目代码
- 复制并启用 `docker-entrypoint.sh`
- 使用入口脚本启动应用

同时需要保证：

- 构建上下文不包含 `.env`
- 构建上下文不包含本地 `data/`
- 不依赖 Compose 提供任何额外文件准备逻辑

### 6. `.dockerignore` 设计

必须新增或补充以下忽略项：

- `.env`
- `data/`
- 保留现有：`tmp/`、`*.log`、虚拟环境、缓存等

这样可以避免：

- 本地 secrets 进入镜像
- 本地运行态数据污染镜像
- 本地测试数据在云镜像中产生假状态

### 7. Compose 设计

`docker-compose.yml` 保留，但角色明确为本地 / VPS 入口。

要求：

- 保留 `env_file: .env`
- 保留或简化 `environment` 映射，但最终行为必须与 `Dockerfile` 路径一致
- 挂载：`./data:/app/data`
- 不再额外挂载根目录下的 `allowed_users.txt`、`user_settings.json`、`tmp/` 或日志文件

### 8. 文档设计

#### `.env.example`

补充说明：

- 哪些变量是必填
- 哪些变量是可选
- ClawCloud 和 Compose 都使用同一套环境变量

#### `README.md`

需要拆成两条部署路径：

1. **ClawCloud 部署**
   - 使用 Dockerfile
   - 配置环境变量
   - 挂载持久化目录到 `/app/data`
   - 说明重建后哪些数据会保留
   - 明确该部署方式适用于无需 HTTP 监听端口的 worker / background service 场景

2. **Docker Compose 部署**
   - `cp .env.example .env`
   - `docker compose up -d --build`
   - `docker compose logs -f`
   - `docker compose down`

3. **本地直接运行 Python**
   - 明确本地运行时默认使用 `./data`
   - README 的项目结构与说明中不再把仓库根目录下的 `allowed_users.txt`、`user_settings.json` 视为权威路径
   - 说明可变运行时文件统一收口到 `data/`

同时明确：

- 默认持久化的运行时数据包括：
  - `allowed_users.txt`
  - `user_settings.json`
  - `tmp/last_can_biao_xiu_state_*.txt`
  - `strategy.log`
- 如果用户不想持久化日志，应通过日志路径配置或挂载策略单独调整，而不是继续把日志写在项目根目录

### 9. 健康检查策略

本项目当前没有 HTTP 服务端口。

本次设计不为了适配 PaaS 人为增加 Web 服务，只采用以下策略：

- 启动前对关键环境变量做强校验
- 启动时确保必要目录和文件存在
- 依赖容器主进程持续运行作为基本健康信号
- ClawCloud 侧需以前台 worker / background container 模式运行，而不是强制要求 HTTP 监听端口的 web service 模式

如后续确认平台只接受 web 服务与端口健康检查，则需要单独设计最小健康检查方案，不在本次最小闭环范围内。

## 验证方式

### 静态验证

- `bash -n docker-entrypoint.sh`
- `docker compose config`
- 确认 `.dockerignore` 已排除 `.env` 与 `data/`

### 构建验证

- `docker build -t ltt-strategy:test .`
- 预期：镜像构建成功

### 运行验证

#### 缺少必填环境变量时

- 启动应在入口脚本阶段失败
- 应输出明确缺失变量名
- 不应等到 Python 运行中才暴露

#### 首次启动时

- 自动创建 `/app/data`
- 自动创建 `/app/data/tmp`
- 自动创建 `/app/data/allowed_users.txt`
- 自动创建 `/app/data/user_settings.json`
- 首次运行后，参标修信号状态文件应写入 `/app/data/tmp/`
- 首次运行后，日志文件应写入 `/app/data/strategy.log`

#### 升级现有部署时

- 如果挂载目录中已存在 `allowed_users.txt` 和 `user_settings.json`，新镜像启动后必须继续复用这些文件
- 如果升级时旧版本在项目根目录残留运行时文件，而挂载目录中尚无对应文件，迁移逻辑必须把已有数据安全迁入 `/app/data`
- 升级后不应再依赖软链接作为正确性的唯一前提

#### 重建容器后

- 已有订阅用户和用户设置仍保留
- 参标修信号去重状态仍保留
- 日志文件仍位于 `/app/data/strategy.log`
- 使用现有挂载 `data/` 目录重新创建容器后，应用仍可正常启动


## 非目标

- 不引入数据库、Redis、反向代理、监控等新组件
- 不改动策略计算与 Telegram 通知业务逻辑
- 不增加 HTTP 服务仅为了健康检查
- 不为 ClawCloud 和 Compose 维护两套不同代码路径

## 后续实现影响文件

预计需要修改：

- `config.py`
- `main.py`
- `notifier.py`
- `strategy_sig.py`
- `docker-entrypoint.sh`
- `docker-compose.yml`
- `.dockerignore`
- `.env.example`
- `README.md`

## 结论

这次改造的核心不是“再补一个 Docker 配置”，而是把 **运行时状态边界** 从“靠约定和软链接勉强维持”升级为“代码、容器、文档三层一致”。

只有这样，ClawCloud 单 Docker 部署和本地 Compose 才能真正拉通，用户数据持久化才是可验证、可维护、可复用的闭环。