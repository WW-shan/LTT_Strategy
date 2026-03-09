# Docker Compose 一键部署 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在保持当前单服务运行结构不变的前提下，完善 Docker Compose 一键部署，使其具备启动前环境校验、最小必要持久化和与实现一致的部署文档。

**Architecture:** 保留现有 `Dockerfile` + `docker-compose.yml` + `python main.py` 主流程，只在容器入口前增加一层很薄的启动脚本用于环境校验与文件准备。Compose 仅持久化 `allowed_users.txt` 和 `user_settings.json`，不持久化 `tmp/` 和日志，以最小改动提升部署可靠性。

**Tech Stack:** Docker, Docker Compose, shell entrypoint, Python 3.11, README 文档

---

### Task 1: 增加容器启动前校验脚本

**Files:**
- Create: `docker-entrypoint.sh`
- Verify: `Dockerfile:1-13`
- Verify: `.env.example:1-13`

**Step 1: 编写启动脚本**

创建 `docker-entrypoint.sh`，内容包含：

```sh
#!/bin/sh
set -eu

required_vars="TG_BOT_TOKEN TG_CHAT_ID SUBSCRIBE_PASSWORD"

for var in $required_vars; do
    eval "value=\${$var:-}"
    if [ -z "$value" ]; then
        echo "[startup-check] Missing required environment variable: $var" >&2
        exit 1
    fi
done

mkdir -p /app/data

if [ ! -f /app/data/allowed_users.txt ]; then
    : > /app/data/allowed_users.txt
fi

if [ ! -f /app/data/user_settings.json ]; then
    printf '{}' > /app/data/user_settings.json
fi

ln -sf /app/data/allowed_users.txt /app/allowed_users.txt
ln -sf /app/data/user_settings.json /app/user_settings.json

exec python main.py
```

**Step 2: 复查脚本行为**

确认脚本只做三件事：
- 校验必填环境变量
- 准备持久化文件
- 启动主程序

禁止加入额外业务逻辑。

**Step 3: 本地语法级检查脚本内容**

Run: `bash -n docker-entrypoint.sh`
Expected: 无输出，表示 shell 语法通过。

---

### Task 2: 接入 Dockerfile 入口脚本

**Files:**
- Modify: `Dockerfile:1-13`
- Verify: `docker-entrypoint.sh`

**Step 1: 复制启动脚本进镜像**

将 `Dockerfile` 从：

```dockerfile
COPY . .

CMD ["python", "main.py"]
```

改为：

```dockerfile
COPY . .
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]
```

**Step 2: 确认主程序启动路径不变**

确认真正启动应用的仍然是：

```sh
exec python main.py
```

即只是在 Docker 入口前增加校验层，不改 Python 主流程。

**Step 3: 构建语法级验证**

Run: `docker build -t ltt-strategy:test .`
Expected: 镜像构建成功。

---

### Task 3: 为 Compose 增加最小必要持久化与更清晰的环境加载

**Files:**
- Modify: `docker-compose.yml:1-14`
- Verify: `.env.example:1-13`

**Step 1: 增加 env_file**

在服务定义中加入：

```yaml
env_file:
  - .env
```

保留现有 environment 默认值写法，除非确认完全冗余后再简化。

**Step 2: 增加持久化目录挂载**

在 `docker-compose.yml` 中加入：

```yaml
volumes:
  - ./data:/app/data
```

**Step 3: 保持持久化范围最小**

确认只通过 `/app/data` 间接承载：
- `allowed_users.txt`
- `user_settings.json`

不要挂载：
- `/app/tmp`
- `strategy.log`
- 整个项目目录

**Step 4: Compose 配置静态校验**

Run: `docker compose config`
Expected: 成功输出规范化配置，无语法错误。

---

### Task 4: 验证缺失环境变量时会快速失败

**Files:**
- Verify: `docker-entrypoint.sh`
- Verify: `docker-compose.yml`
- Verify: `.env.example`

**Step 1: 构造缺变量场景**

使用临时环境覆盖方式验证，例如清空一个必填变量：

```bash
TG_BOT_TOKEN= docker compose run --rm ltt-strategy
```

或使用等价方式确保容器启动时缺少必填值。

**Step 2: 确认失败信息明确**

Expected: 输出类似：

```text
[startup-check] Missing required environment variable: TG_BOT_TOKEN
```

并以非 0 状态退出。

**Step 3: 确认不是 Python 运行期才报错**

Expected: 失败发生在入口脚本阶段，而不是 `main.py` 深处。

---

### Task 5: 验证持久化文件准备逻辑

**Files:**
- Verify: `docker-entrypoint.sh`
- Verify: `docker-compose.yml`

**Step 1: 启动前删除本地 `data/`（仅在测试目录内）**

如无 `data/` 目录，可直接继续；如需测试，使用临时环境确保不会误删用户现有数据。

**Step 2: 启动容器**

Run: `docker compose up -d --build`
Expected: 容器成功启动。

**Step 3: 检查持久化文件是否已准备**

Run: `ls data`
Expected: 至少可见：
- `allowed_users.txt`
- `user_settings.json`

**Step 4: 确认未扩大发散到其他持久化内容**

Expected:
- `tmp/` 不在 `data/` 中自动持久化
- `strategy.log` 不在 `data/` 中自动持久化

---

### Task 6: 更新 README 的一键部署文档

**Files:**
- Modify: `README.md:118-158`
- Verify: `docker-compose.yml`
- Verify: `docker-entrypoint.sh`

**Step 1: 更新部署说明**

在 Docker 一键启动部分补充：
- 必填环境变量缺失会导致容器启动失败
- 持久化的是 `allowed_users.txt` 和 `user_settings.json`
- `tmp/` 和日志默认不持久化

**Step 2: 保持命令与实际实现一致**

文档保留并确认以下命令仍正确：

```bash
cp .env.example .env
docker compose up -d --build
docker compose logs -f
docker compose down
```

**Step 3: 文档一致性复查**

Expected: README 中的部署描述与 `docker-compose.yml` / `Dockerfile` / `docker-entrypoint.sh` 一致，不出现“全部状态持久化”之类错误描述。

---

### Task 7: 全局复核并整理变更说明

**Files:**
- Verify: `docker-entrypoint.sh`
- Verify: `Dockerfile`
- Verify: `docker-compose.yml`
- Verify: `README.md`

**Step 1: 全量静态校验**

Run: `bash -n docker-entrypoint.sh && docker compose config`
Expected: 均成功，无输出错误。

**Step 2: 构建验证**

Run: `docker build -t ltt-strategy:test .`
Expected: 镜像构建成功。

**Step 3: 总结变更**

输出变更摘要：
- 新增了什么
- 为什么属于最小完善
- 哪些状态会持久化，哪些不会
- 缺变量时如何失败

**Step 4: 准备提交（仅在用户要求时）**

如果用户要求提交，再执行：

```bash
git add Dockerfile docker-compose.yml docker-entrypoint.sh README.md docs/plans/2026-03-10-docker-compose-one-click-deploy-design.md docs/plans/2026-03-10-docker-compose-one-click-deploy-plan.md
git commit -m "feat: improve docker compose one-click deployment"
```
