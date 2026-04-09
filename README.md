# CK - Code Knowledge

代码仓库知识图谱分析与文档生成系统。支持多语言代码解析、知识图谱构建、交互式代码问答和自动设计文档生成。

## 功能特性

- **多语言代码解析** — Python / Java / C / C++ / JavaScript / Go / Rust（Tree-sitter + Spoon + CDT）
- **知识图谱构建** — 模块 / 文件 / 符号 / 关系四层索引，稳定 ID 体系
- **向量语义检索** — pgvector 嵌入索引，sentence-transformers 或 OpenAI 编码
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
| 向量存储 | pgvector |
| 代码解析 | Tree-sitter (多语言) |
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

# 配置环境变量（可选，有默认值）
cp .env.example .env
# 编辑 .env 设置 DATABASE_URL, LLM_API_BASE 等
```

### 数据库

```bash
# 确保 PostgreSQL 已安装并启用 pgvector 扩展
psql -c "CREATE DATABASE ck;"
psql -d ck -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### 运行

```bash
# 启动服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 运行端到端 Demo（无需数据库）
python3 scripts/demo.py
```

### API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/repo/scan` | 扫描代码仓库，构建图索引 |
| POST | `/qa/ask` | 交互式代码问答 |
| POST | `/doc/plan` | 生成文档骨架 |
| POST | `/doc/generate` | 生成完整设计文档 |
| GET | `/doc/{repo_id}/sections` | 获取文档段落列表 |
| GET | `/metrics` | 获取运行时指标 |
| POST | `/metrics/reset` | 重置指标 |
| GET | `/health` | 健康检查 |

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

所有配置项支持通过环境变量或 `.env` 文件覆盖。

## 开发

### 运行测试

```bash
python3 -m pytest app/tests/ -v
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
