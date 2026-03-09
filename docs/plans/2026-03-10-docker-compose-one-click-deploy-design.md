# 2026-03-10 Docker Compose 一键部署设计

## 目标

在不改变项目核心运行方式的前提下，完善当前 Docker Compose 部署能力，使用户可以通过更可靠的 `docker compose up -d --build` 完成一键部署，并在配置缺失时得到明确失败信号。

## 用户确认的约束

- 采用“最小完善”方案，不做重型生产化改造
- 继续保持单服务 Compose 结构
- 只持久化以下运行状态：
  - `allowed_users.txt`
  - `user_settings.json`
- 不持久化以下内容：
  - `tmp/`
  - `strategy.log`
- 必填环境变量缺失时，容器启动应立即失败并给出明确提示

## 当前现状

### 已有能力
- 项目已经有 `Dockerfile`
- 项目已经有 `docker-compose.yml`
- README 已提供 `.env` 准备和 `docker compose up -d --build` 的基本说明

### 现有缺口
- Compose 当前仅注入环境变量，没有持久化订阅与用户配置文件
- 当前镜像直接执行 `python main.py`，缺少启动前环境校验
- 如果关键环境变量未配置，失败位置偏后，用户不容易第一时间理解原因
- README 尚未明确哪些运行状态会持久化、哪些不会

## 方案对比

### 方案 1：最小完善（采用）
- 保留单服务 Compose
- 增加启动前环境变量校验
- 增加订阅与用户配置文件持久化
- 更新 README 说明真实部署行为

**优点：**
- 改动小，风险低
- 不改变现有 Python 主流程
- 最符合当前项目体量

### 方案 2：中等增强
- 在方案 1 基础上增加更重的初始化流程、更多启动辅助逻辑

**缺点：**
- 超出当前“最小完善”的目标

### 方案 3：生产化加强
- 引入更严格的运维与部署分层设计

**缺点：**
- 对当前项目过重，不符合已确认范围

## 设计

### 1. 容器启动结构
- 保留 `Dockerfile` 构建 Python 运行镜像的方式
- 不改变应用主入口仍然执行 `python main.py`
- 在主程序启动前增加一层很薄的启动入口，用于：
  1. 校验关键环境变量
  2. 确保持久化目标文件存在
  3. 再执行主程序

### 2. 环境变量校验
启动前必须校验：
- `TG_BOT_TOKEN`
- `TG_CHAT_ID`
- `SUBSCRIBE_PASSWORD`

若任意项缺失：
- 打印明确错误信息
- 以非 0 状态退出

这样可以避免“容器表面启动成功，但实际不可用”的假成功状态。

### 3. 持久化策略
Compose 只持久化：
- `allowed_users.txt`
- `user_settings.json`

不持久化：
- `tmp/`
- `strategy.log`

这样既保留用户订阅和个性化设置，又避免把临时状态和日志引入长期挂载。

### 4. 健康检查策略
本项目当前没有 HTTP 服务端口。

为保持最小改动，不额外引入新的 Web 健康检查接口，也不为了 healthcheck 修改应用行为。

本次设计采用：
- 依赖“启动前强校验”保证部署失败尽早暴露
- 不新增 Docker healthcheck 端点或额外服务

### 5. 用户操作路径
目标部署路径保持简洁：

```bash
cp .env.example .env
# 编辑 .env
docker compose up -d --build
docker compose logs -f
```

停止服务：

```bash
docker compose down
```

## 需要修改的文件

- `docker-compose.yml`
- `Dockerfile`
- 可能新增一个很薄的启动脚本（如 shell entrypoint）
- `README.md`

## 验证方式

- 静态检查 Compose 与 Dockerfile 配置是否一致
- 校验启动脚本在缺失环境变量时会失败
- 校验持久化挂载路径与应用实际读写路径一致
- 更新 README，确保文档与实现一致

## 非目标

- 不引入数据库、反向代理、监控、告警等新组件
- 不重构 Python 主程序架构
- 不增加 HTTP 服务只为适配 Docker healthcheck
- 不把临时状态或日志纳入默认持久化范围
