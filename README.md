# CK - Code Knowledge

代码仓库知识图谱分析与文档生成系统。支持多语言代码解析、知识图谱构建、交互式代码问答和自动设计文档生成。

## 功能特性

- **多语言代码解析** — Python / Java / C / C++ / JavaScript / Go / Rust（Python AST + 轻量解析器 fallback）
- **知识图谱构建** — 模块 / 文件 / 符号 / 关系四层索引，稳定 ID 体系
- **增量索引** — 基于文件哈希复用未变化文件，支持 Git changed-only 扫描、删除文件清理
- **向量语义检索** — pgvector 嵌入索引，sentence-transformers 或 OpenAI 编码；SQLite demo/test 环境支持 Python 侧向量搜索
- **交互式代码问答** — 锚点定位 → 上下文检索 → 多策略路由 → LLM 生成
- **自动设计文档生成** — 骨架规划 → 段落生成 → PlantUML 图表 → 一致性审查
- **高级降级模式** — 部分回答、多候选、引导式追问；低置信度标注、段落级降级
- **可观测性** — 结构化 JSON 日志、指标采集（/metrics API）、请求链路追踪

## 技术栈

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.11+ |
| Web 框架 | FastAPI + Uvicorn |
| 数据校验 | Pydantic v2 |
| 元数据存储 | PostgreSQL |
| 向量存储 | pgvector；SQLite 测试模式支持 JSON 向量 |
| 代码解析 | Python AST + 轻量多语言解析器 fallback |
| LLM 接口 | OpenAI-compatible (Ollama / vLLM / 国产模型) |
| 包管理 | uv |

## 快速开始

### 环境准备

```bash
# 克隆仓库
git clone https://github.com/hejian0818/ck.git
cd ck

# 安装依赖
uv sync

# 安装开发/测试依赖
uv sync --extra dev

# 配置环境变量（可选，有默认值）
cp .env.example .env
# 编辑 .env 设置 DATABASE_URL, LLM_API_BASE 等
```

### 数据库

```bash
# 确保 PostgreSQL 已安装并启用 pgvector 扩展
psql -c "CREATE DATABASE ck;"
psql -d ck -c "CREATE EXTENSION IF NOT EXISTS vector;"

# 执行数据库迁移
uv run alembic upgrade head
```

### 运行

```bash
# 启动服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 运行端到端 Demo（无需数据库）
python3 scripts/demo.py
```

### Docker Compose 部署

一条命令启动 API + PostgreSQL + pgvector：

```bash
docker compose up --build
```

健康检查：

```bash
curl http://localhost:8000/health
```

Compose 会把当前仓库只读挂载到容器内：

```text
/workspace/repos/codewiki
```

可以直接扫描当前项目：

```bash
curl -X POST http://localhost:8000/repo/scan \
  -H "Content-Type: application/json" \
  -d '{
    "repo_path": "/workspace/repos/codewiki",
    "branch": "main",
    "incremental": true
  }'
```

默认 Compose 配置设置 `ENABLE_VECTOR_INDEXING=false`，避免首次扫描时下载 embedding 模型。需要 pgvector 嵌入索引时，把 `docker-compose.yml` 里的值改为 `true`，并确保容器能访问对应 embedding 模型或 OpenAI-compatible embedding 服务。

API 容器启动时会自动执行：

```bash
alembic upgrade head
```

### API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/repo/scan` | 扫描代码仓库，构建图索引 |
| POST | `/repo/scan-async` | 后台扫描代码仓库，返回任务 ID |
| GET | `/repo/tasks/{task_id}` | 查询后台索引任务状态 |
| POST | `/qa/ask` | 交互式代码问答 |
| POST | `/doc/plan` | 生成文档骨架 |
| POST | `/doc/generate` | 生成完整设计文档 |
| GET | `/doc/{repo_id}/sections` | 获取文档段落列表 |
| GET | `/metrics` | 获取运行时指标 |
| POST | `/metrics/reset` | 重置指标 |
| GET | `/health` | 健康检查 |

### 索引构建

全量构建：

```bash
uv run python scripts/build_index.py --repo-path /path/to/repo --branch main
```

默认开启哈希增量复用：如果仓库已经索引过，未变化文件会从旧图复用，只重新解析内容变化的文件。

只扫描当前工作树相对 `HEAD` 的 Git 变更：

```bash
uv run python scripts/build_index.py --repo-path /path/to/repo --changed-only
```

指定比较基准：

```bash
uv run python scripts/build_index.py --repo-path /path/to/repo --changed-only --base-ref origin/main
```

对应 API 请求：

```json
POST /repo/scan
{
  "repo_path": "/path/to/repo",
  "branch": "main",
  "incremental": true,
  "changed_only": true,
  "base_ref": "HEAD"
}
```

后台索引：

```json
POST /repo/scan-async
{
  "repo_path": "/path/to/repo",
  "branch": "main",
  "incremental": true,
  "changed_only": true,
  "base_ref": "HEAD"
}
```

返回：

```json
{
  "task_id": "8ddfb0c842c449f5aa3de8f1e6c3e0ac",
  "status": "queued"
}
```

查询任务：

```bash
curl http://localhost:8000/repo/tasks/8ddfb0c842c449f5aa3de8f1e6c3e0ac
```

任务状态包括 `queued`、`running`、`success`、`failed`。成功后 `result` 字段包含和 `/repo/scan` 相同的构建统计。

`changed_only` 会保留旧索引中的未变化文件，只重建 Git 变更文件；已删除源码文件会从图索引和向量索引中清理。

响应字段：

| 字段 | 说明 |
|------|------|
| `parsed_files` | 本次实际解析的文件数 |
| `reused_files` | 从旧图复用的文件数 |
| `deleted_files` | 本次从索引中移除的文件数 |
| `scanned_files` | 本次 Git 变更扫描命中的现存源码文件数 |

## 架构说明

```
代码仓库 → cleanarch 解析 → graphcode.json
    ↓
四层索引（模块/文件/符号/关系）
    ↓
向量嵌入（pgvector）+ 图索引
    ↓
┌─────────────────────┐
│ QA Agent            │  锚点定位 → 检索 → 策略路由 → LLM 生成
│ (交互式问答)        │  4 种策略: S1(默认) S2(增强) S3(推断) S4(降级)
├─────────────────────┤
│ Doc Agent           │  骨架规划 → 段落检索 → 段落生成 → PlantUML
│ (文档生成)          │  一致性审查: 结构/内容/图表三维校验
└─────────────────────┘
    ↓
Memory 系统: Anchor Memory / Retrieval Memory / Focus Memory / Task Memory
```

## 配置参考

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `DATABASE_URL` | `postgresql://localhost/ck` | 数据库连接 |
| `VECTOR_DIMENSION` | `768` | 向量维度 |
| `ENABLE_VECTOR_INDEXING` | `True` | PostgreSQL 模式下是否构建 pgvector 嵌入索引 |
| `EMBEDDING_PROVIDER` | `sentence-transformer` | 嵌入提供方 |
| `EMBEDDING_MODEL` | `BAAI/bge-base-en-v1.5` | 嵌入模型 |
| `EMBEDDING_BATCH_SIZE` | `32` | 嵌入批量大小 |
| `LLM_API_BASE` | `http://localhost:11434/v1` | LLM API 地址 |
| `LLM_MODEL` | `qwen2.5-coder:7b` | LLM 模型 |
| `LLM_MAX_RETRIES` | `3` | LLM 最大重试次数 |
| `LLM_TIMEOUT` | `30` | LLM 调用超时（秒） |
| `DOC_MAX_SECTIONS` | `50` | 文档最大段落数 |
| `DOC_DIAGRAM_ENABLED` | `True` | 是否生成图表 |
| `DOC_RETRIEVAL_TOP_K` | `10` | 文档检索 top-k |
| `CACHE_EMBEDDING_SIZE` | `1000` | 嵌入缓存大小 |
| `CACHE_GRAPH_TTL` | `60` | 图查询缓存 TTL（秒） |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `API_KEY` | `""` | 可选 API Key；设置后写操作需传 `X-API-Key` 或 `Authorization: Bearer ...` |
| `REPO_SCAN_ALLOWED_ROOTS` | `""` | 允许扫描的本地根路径，多个路径用 `:` 分隔 |
| `REPO_SCAN_MAX_FILES` | `5000` | 单次扫描允许的最大源码文件数，`0` 表示不限制 |
| `REPO_SCAN_MAX_FILE_BYTES` | `1000000` | 单个源码文件最大字节数，超过会跳过，`0` 表示不限制 |

所有配置项支持通过环境变量或 `.env` 文件覆盖。

## 开发

### 运行测试

```bash
uv run python -m pytest app/tests/ -v
```

### 质量检查

```bash
uv run ruff check app scripts
uv run mypy
uv run python -m compileall app scripts
uv run alembic upgrade head
```

当前主分支验证状态：

```text
170 passed, 1 skipped
```

### 项目结构

```
ck/
  app/
    api/          # FastAPI 端点 (qa, doc, repo, metrics)
    core/         # 配置、日志、指标、常量
    models/       # Pydantic 模型
    services/
      cleanarch/  # 多语言代码解析
      indexing/   # 索引构建、嵌入生成
      retrieval/  # 检索、排序、图扩展
      agents/     # QA Agent, Doc Agent, 策略路由
      context/    # 上下文构建
      memory/     # 会话记忆管理
      review/     # 文档审查
      diagrams/   # PlantUML 生成
    storage/      # 数据库访问、向量存储
    tests/        # 单元测试
  scripts/        # 演示和工具脚本
  data/           # 数据存储
```

## License

MIT
