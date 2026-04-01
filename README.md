# CodeWiki

CodeWiki 是一个单代码仓设计文档生成与代码问答系统。Phase 1 目标是跑通 `cleanarch -> graphcode.json -> 索引 -> QA` 的最小闭环。

## Features

- 多语言解析适配层，当前可直接解析 Python，Java 和 C/C++ 适配器保留为 mock 接口
- 生成 `GraphCode` 结构，包含模块、文件、符号、关系、span
- PostgreSQL schema 与仓库存储层
- 显式代码片段落锚、基础结构化检索、上下文构造
- 基础 QA Agent 与 OpenAI-compatible LLM 接口
- FastAPI API、CLI 脚本、测试仓库与单元测试

## Tech Stack

- Python 3.11+
- FastAPI
- Pydantic v2
- PostgreSQL + pgvector
- SQLAlchemy
- Tree-sitter
- OpenAI-compatible API

## Installation

1. 安装 Python 3.11+。
2. 安装 `uv`。
3. 安装并启动 PostgreSQL，创建数据库并启用 `pgvector`。
4. 在项目根目录执行：

```bash
uv sync
cp .env.example .env
```

## Configuration

`.env` 示例：

```env
DATABASE_URL=postgresql://localhost/codewiki
VECTOR_DIMENSION=768
LOG_LEVEL=INFO
LOG_FORMAT=json
LLM_API_BASE=http://localhost:11434/v1
LLM_API_KEY=dummy
LLM_MODEL=qwen2.5-coder:7b
```

## Run

启动 API：

```bash
uv run uvicorn app.main:app --reload
```

构建索引：

```bash
uv run python scripts/build_index.py --repo-path data/test_repo --branch main
```

运行 Demo：

```bash
uv run python scripts/run_demo.py
```

运行测试：

```bash
python -m unittest discover -s app/tests
```

## API

- `POST /repo/build-index`
- `POST /qa/ask`
- `GET /qa/session/{session_id}`
- `POST /qa/session/{session_id}/reset`

启动服务后可访问交互式 API 文档：

- `http://127.0.0.1:8000/docs`

## Example QA Request

```bash
curl -X POST http://127.0.0.1:8000/qa/ask \
  -H 'Content-Type: application/json' \
  -d '{
    "repo_id": "repo_sample",
    "session_id": "demo-session",
    "question": "这个方法做什么？",
    "selection": {
      "file_path": "data/test_repo/app_core/services.py",
      "line_start": 6,
      "line_end": 7
    }
  }'
```

## Project Structure

```text
app/
  api/          FastAPI endpoints
  core/         config, logging, thresholds
  models/       graph, anchor, QA models
  services/     parsing, retrieval, context, agents, memory
  storage/      PostgreSQL schema and repository layer
  tests/        unit tests
scripts/        CLI tools
data/           test repo and sample graphcode
```
