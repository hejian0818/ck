# Phase 1 Development Tasks

## Overview
Phase 1 目标：跑通 cleanarch -> graphcode.json -> 索引 -> QA 的最小闭环。

## Task 1: Project Initialization
### Requirements
- 使用 uv 初始化 Python 项目
- 创建 pyproject.toml，配置依赖：
  - fastapi
  - uvicorn
  - pydantic >= 2.0
  - psycopg2-binary (PostgreSQL driver)
  - pgvector (PostgreSQL vector extension)
  - sqlalchemy
  - tree-sitter
  - tree-sitter-python
  - tree-sitter-javascript
  - tree-sitter-go
  - tree-sitter-rust
- 创建项目目录结构（参考 CLAUDE.md）
- 创建 .gitignore（Python 标准 + data/ + .env）
- 创建 README.md（项目说明、安装步骤、运行方法）

### Acceptance Criteria
- `uv sync` 可以成功安装所有依赖
- 目录结构完整
- README 包含基本说明

### Commit Message
```
feat: initialize project structure with uv and dependencies
```

---

## Task 2: Core Data Models
### Requirements
在 `app/models/graph_objects.py` 中定义核心数据模型：

#### RepoMeta
- repo_id: str
- repo_path: str
- branch: str
- commit_hash: str
- scan_time: datetime

#### Module
- id: str (格式: M_{name})
- name: str
- path: str
- metadata: dict

#### File
- id: str (格式: F_{name})
- name: str
- path: str (相对仓库根目录)
- module_id: str
- language: str
- start_line: int
- end_line: int

#### Symbol
- id: str (格式: S_{name})
- name: str
- qualified_name: str
- type: str (method/function/class/interface/variable)
- signature: str
- file_id: str
- module_id: str
- start_line: int
- end_line: int
- visibility: str (public/private/protected)
- doc: str

#### Relation
- id: str (格式: R_{number})
- relation_type: str (calls/extends/implements/depends_on/references)
- source_id: str
- target_id: str
- source_type: str
- target_type: str
- source_module_id: str
- target_module_id: str

#### Span
- file_path: str
- line_start: int
- line_end: int
- module_id: str
- file_id: str
- symbol_id: Optional[str]
- node_type: str (module/file/symbol)

#### GraphCode (顶层容器)
- repo_meta: RepoMeta
- modules: List[Module]
- files: List[File]
- symbols: List[Symbol]
- relations: List[Relation]
- spans: List[Span]

### Acceptance Criteria
- 所有模型使用 Pydantic BaseModel
- 所有字段有类型注解
- 可以序列化为 JSON
- 可以从 JSON 反序列化

### Commit Message
```
feat: define core data models for graphcode.json
```

---

## Task 3: Configuration Management
### Requirements
在 `app/core/config.py` 中创建配置管理：

#### Settings (Pydantic BaseSettings)
- DATABASE_URL: str
- VECTOR_DIMENSION: int = 768
- LOG_LEVEL: str = "INFO"
- LOG_FORMAT: str = "json"
- LLM_API_BASE: str
- LLM_API_KEY: str
- LLM_MODEL: str

#### Thresholds
在 `app/core/thresholds.py` 中定义所有阈值：
- ANCHOR_CONFIDENCE_STRONG: float = 0.80
- ANCHOR_CONFIDENCE_WEAK: float = 0.60
- RETRIEVAL_CONCENTRATION: float = 0.55
- EVIDENCE_SUFFICIENT: float = 0.60
- EVIDENCE_ENHANCEMENT: float = 0.40
- EXPANSION_GAIN: float = 0.35
- RESULT_CONSISTENCY: float = 0.55

#### Logging
在 `app/core/logging.py` 中配置结构化日志：
- JSON 格式
- 包含 timestamp, level, message, context

### Acceptance Criteria
- 可以从环境变量读取配置
- 提供 .env.example 示例文件
- 日志输出为 JSON 格式
- 所有阈值集中管理

### Commit Message
```
feat: add configuration management and structured logging
```

---

## Task 4: Multi-language Parser Adapter Architecture
### Requirements
在 `app/services/cleanarch/` 中创建解析器适配层：

#### parser_adapter.py
定义统一接口：
```python
class ParserAdapter(ABC):
    @abstractmethod
    def parse_file(self, file_path: str) -> ParseResult:
        """解析单个文件，返回符号和关系"""
        pass

    @abstractmethod
    def supports_language(self, language: str) -> bool:
        """判断是否支持该语言"""
        pass
```

#### ParseResult
- symbols: List[Symbol]
- relations: List[Relation]
- spans: List[Span]

#### 实现三个适配器
1. **TreeSitterAdapter** (app/services/cleanarch/treesitter_adapter.py)
   - 支持: Python, JavaScript, Go, Rust
   - 使用 tree-sitter 解析
   - 提取函数、类、方法定义
   - 提取调用关系

2. **SpoonAdapter** (app/services/cleanarch/spoon_adapter.py)
   - 支持: Java
   - 通过 subprocess 调用 Spoon CLI（初期可以 mock）
   - 提取类、方法、接口
   - 提取继承、实现、调用关系

3. **CDTAdapter** (app/services/cleanarch/cdt_adapter.py)
   - 支持: C, C++
   - 通过 subprocess 调用 CDT（初期可以 mock）
   - 提取函数、类、结构体
   - 提取调用和依赖关系

#### ParserFactory
根据文件扩展名选择合适的适配器。

### Acceptance Criteria
- 统一的 ParserAdapter 接口
- TreeSitterAdapter 可以解析 Python 文件（至少提取函数定义）
- SpoonAdapter 和 CDTAdapter 提供 mock 实现
- ParserFactory 可以根据文件类型选择适配器

### Commit Message
```
feat: implement multi-language parser adapter architecture
```

---

## Task 5: Repository Scanner
### Requirements
在 `app/services/cleanarch/scanner.py` 中实现仓库扫描器：

#### RepoScanner
- scan_repository(repo_path: str) -> List[str]
  - 递归扫描目录
  - 过滤忽略的目录和文件
  - 返回所有源码文件路径

#### 必须过滤的目录
- .git
- node_modules
- dist, build, target
- __pycache__, .pytest_cache
- venv, .venv

#### 必须过滤的文件
- 二进制文件
- 图片、视频
- .min.js, .bundle.js

### Acceptance Criteria
- 可以扫描指定目录
- 正确过滤无关文件
- 返回相对路径列表

### Commit Message
```
feat: implement repository scanner with ignore patterns
```

---

## Task 6: Graph Builder
### Requirements
在 `app/services/cleanarch/graph_builder.py` 中实现图构建器：

#### GraphBuilder
- build_graph(repo_path: str) -> GraphCode
  1. 扫描仓库获取文件列表
  2. 推断模块划分（按目录结构）
  3. 对每个文件选择适配器解析
  4. 统一分配 ID
  5. 构建 span 映射
  6. 组装 GraphCode

#### 模块推断规则
- 顶层目录作为模块
- src/main/java/com/example/order -> module: order
- 如果没有明显模块结构，整个仓库作为一个模块

#### ID 生成规则
- Module: M_{module_name}
- File: F_{file_name_without_ext}_{hash_suffix}
- Symbol: S_{qualified_name}_{hash_suffix}
- Relation: R_{sequential_number}

### Acceptance Criteria
- 可以解析一个小型测试仓库
- 生成完整的 GraphCode 对象
- 所有对象有唯一 ID
- Span 映射完整

### Commit Message
```
feat: implement graph builder for multi-language repos
```

---

## Task 7: Database Schema and Storage
### Requirements
在 `app/storage/` 中实现数据库访问层：

#### schema.sql
创建 PostgreSQL 表结构：
- repos (repo_id, repo_path, branch, commit_hash, scan_time)
- modules (id, repo_id, name, path, metadata)
- files (id, repo_id, module_id, name, path, language, start_line, end_line)
- symbols (id, repo_id, file_id, module_id, name, qualified_name, type, signature, start_line, end_line, visibility, doc)
- relations (id, repo_id, relation_type, source_id, target_id, source_type, target_type, source_module_id, target_module_id)
- spans (repo_id, file_path, line_start, line_end, module_id, file_id, symbol_id, node_type)

#### repositories.py
使用 SQLAlchemy 实现 CRUD：
- save_graphcode(graphcode: GraphCode)
- get_module_by_id(module_id: str) -> Module
- get_file_by_id(file_id: str) -> File
- get_symbol_by_id(symbol_id: str) -> Symbol
- get_relations_by_source(source_id: str) -> List[Relation]
- find_span(file_path: str, line_start: int, line_end: int) -> List[Span]

### Acceptance Criteria
- 数据库表结构完整
- 可以保存 GraphCode 到数据库
- 可以按 ID 查询对象
- Span 查询支持行范围匹配

### Commit Message
```
feat: implement PostgreSQL schema and repository layer
```

---

## Task 8: Anchor System
### Requirements
在 `app/models/anchor.py` 中定义锚点模型：

#### Anchor
- level: Literal["module", "file", "symbol", "none"]
- source: Literal["explicit_span", "explicit_file", "explicit_module", "name_match", "memory_inherit", "retrieval_infer", "none"]
- confidence: float
- module_id: Optional[str]
- file_id: Optional[str]
- symbol_id: Optional[str]
- file_path: Optional[str]
- line_start: Optional[int]
- line_end: Optional[int]

在 `app/services/retrieval/anchor_resolver.py` 中实现锚点解析：

#### AnchorResolver
- resolve_anchor(question: str, selection: Optional[CodeSelection], memory: AnchorMemory) -> Anchor
  1. 如果有 selection (file_path + line range)，走 span 落锚
  2. 否则返回 none 锚点（Phase 1 暂不实现名称匹配和继承）

#### Span 落锚逻辑
- 查询 spans 表，找到覆盖该行范围的所有对象
- 优先返回最小包围区间
- 优先级: method/function > class/interface > file

### Acceptance Criteria
- 可以根据代码片段定位到 symbol
- 可以定位到 file
- 可以定位到 module
- 返回置信度

### Commit Message
```
feat: implement anchor resolution system
```

---

## Task 9: Basic Retrieval
### Requirements
在 `app/services/retrieval/retriever.py` 中实现基础检索：

#### Retriever
- retrieve(anchor: Anchor, question: str) -> RetrievalResult
  - 根据锚点级别收缩范围
  - 结构化召回当前对象及其直接关系
  - Phase 1 暂不实现向量召回

#### 范围收缩规则
- symbol 锚点: 当前 symbol + 当前 file + 当前 module
- file 锚点: 当前 file + 当前 module
- module 锚点: 当前 module + 邻接模块
- none: 不做范围限制（Phase 1 返回空）

#### RetrievalResult
- anchor: Anchor
- current_object: Union[Module, File, Symbol]
- related_objects: List[Union[Module, File, Symbol]]
- relations: List[Relation]

### Acceptance Criteria
- 可以根据 symbol 锚点检索相关对象
- 可以获取一跳关系（callers/callees）
- 返回结构化结果

### Commit Message
```
feat: implement basic structured retrieval
```

---

## Task 10: Context Builder
### Requirements
在 `app/services/context/context_builder.py` 中实现上下文构造：

#### ContextBuilder
- build_context(question: str, selection: Optional[CodeSelection], anchor: Anchor, retrieval_result: RetrievalResult) -> str
  - 组装结构化上下文
  - 按优先级裁剪（Phase 1 暂不实现复杂裁剪）

#### 上下文结构
```
当前问题: {question}

当前代码片段:
{code_snippet}

当前锚点:
- 层级: {anchor.level}
- 对象: {anchor.symbol_id or anchor.file_id or anchor.module_id}

局部结构:
- 所属文件: {file_info}
- 所属模块: {module_info}

局部关系:
- 调用者: {callers}
- 被调用者: {callees}

请回答上述问题。
```

### Acceptance Criteria
- 可以组装完整上下文
- 包含代码片段、锚点、关系信息
- 输出格式清晰

### Commit Message
```
feat: implement context builder for QA
```

---

## Task 11: Memory Management (Basic)
### Requirements
在 `app/services/memory/memory_manager.py` 中实现基础记忆管理：

#### AnchorMemory
- current_anchor: Optional[Anchor]

#### MemoryManager
- get_anchor_memory(session_id: str) -> AnchorMemory
- update_anchor_memory(session_id: str, anchor: Anchor)
- clear_memory(session_id: str)

Phase 1 只实现 Anchor Memory，使用内存存储（dict）。

### Acceptance Criteria
- 可以保存和读取锚点记忆
- 支持会话隔离

### Commit Message
```
feat: implement basic anchor memory management
```

---

## Task 12: QA Agent (Basic)
### Requirements
在 `app/services/agents/qa_agent.py` 中实现基础问答 Agent：

#### QAAgent
- answer(question: str, selection: Optional[CodeSelection], session_id: str) -> QAResponse
  1. 确定锚点
  2. 读取记忆
  3. 范围收缩
  4. 首轮召回
  5. 组装上下文
  6. 调用 LLM 生成回答
  7. 回写记忆

#### QAResponse
- answer: str
- anchor: Anchor
- confidence: float
- used_objects: List[str]
- need_more_context: bool

#### LLM 调用
使用 OpenAI-compatible API：
```python
import openai
client = openai.OpenAI(
    base_url=settings.LLM_API_BASE,
    api_key=settings.LLM_API_KEY
)
response = client.chat.completions.create(
    model=settings.LLM_MODEL,
    messages=[{"role": "user", "content": context}]
)
```

### Acceptance Criteria
- 可以回答基于代码片段的问题
- 返回锚点和置信度
- 记录使用的对象

### Commit Message
```
feat: implement basic QA agent with LLM integration
```

---

## Task 13: FastAPI Endpoints
### Requirements
在 `app/api/` 中实现 API 接口：

#### repo.py
- POST /repo/build-index
  - 输入: repo_path, branch
  - 调用 GraphBuilder 构建索引
  - 保存到数据库
  - 返回: build_id, status

#### qa.py
- POST /qa/ask
  - 输入: repo_id, session_id, question, selection (optional)
  - 调用 QAAgent
  - 返回: answer, anchor, confidence, used_objects

#### session.py
- GET /qa/session/{session_id}
  - 返回会话状态
- POST /qa/session/{session_id}/reset
  - 清空会话记忆

#### main.py
创建 FastAPI app，注册路由。

### Acceptance Criteria
- 所有接口可以正常调用
- 请求和响应使用 Pydantic 模型
- 包含基本错误处理

### Commit Message
```
feat: implement FastAPI endpoints for repo indexing and QA
```

---

## Task 14: CLI Scripts
### Requirements
在 `scripts/` 中创建命令行工具：

#### build_index.py
```bash
python scripts/build_index.py --repo-path /path/to/repo --branch main
```
- 调用 GraphBuilder
- 保存到数据库
- 输出统计信息

#### run_demo.py
```bash
python scripts/run_demo.py
```
- 启动 FastAPI 服务
- 提供简单的交互式问答界面

### Acceptance Criteria
- 可以通过命令行构建索引
- 可以启动服务并测试问答

### Commit Message
```
feat: add CLI scripts for indexing and demo
```

---

## Task 15: Testing and Documentation
### Requirements

#### 创建测试仓库
在 `data/test_repo/` 中创建一个小型 Python 测试项目：
- 2-3 个模块
- 5-10 个文件
- 包含函数、类、方法
- 包含调用关系

#### 单元测试
在 `app/tests/` 中创建测试：
- test_scanner.py: 测试仓库扫描
- test_parser.py: 测试解析器
- test_anchor.py: 测试锚点解析
- test_retrieval.py: 测试检索
- test_qa.py: 测试问答（可以 mock LLM）

#### 更新 README.md
- 项目介绍
- 安装步骤
- 配置说明
- 运行示例
- API 文档链接

### Acceptance Criteria
- 测试仓库可以成功解析
- 核心模块有单元测试
- README 完整清晰

### Commit Message
```
feat: add tests and update documentation
```

---

## Phase 1 Acceptance Criteria

### 功能验收
1. ✅ 可以解析测试仓库生成 graphcode.json
2. ✅ 可以构建索引并保存到数据库
3. ✅ 用户选择代码片段后能正确落锚到 symbol/file/module
4. ✅ 可以回答以下问题：
   - "这个方法做什么？"
   - "谁调用了这个方法？"
   - "这个方法属于哪个模块？"
5. ✅ 锚点置信度正确计算
6. ✅ 会话记忆正常工作

### 技术验收
1. ✅ 所有核心模块有类型注解
2. ✅ 所有关键节点有日志
3. ✅ 配置和阈值集中管理
4. ✅ 数据库 schema 完整
5. ✅ API 接口正常工作
6. ✅ 有基本的单元测试

### 交付物
1. ✅ 完整的项目代码
2. ✅ 可运行的 Demo
3. ✅ README 和运行说明
4. ✅ 测试用例
5. ✅ graphcode.json 样例

---

## Development Notes

### PostgreSQL Setup
开发前需要安装并启动 PostgreSQL：
```bash
# macOS
brew install postgresql@16
brew services start postgresql@16

# 创建数据库
createdb ck

# 安装 pgvector 扩展
psql ck -c "CREATE EXTENSION vector;"
```

### Environment Variables
创建 `.env` 文件：
```
DATABASE_URL=postgresql://localhost/ck
LLM_API_BASE=http://localhost:11434/v1  # Ollama example
LLM_API_KEY=dummy
LLM_MODEL=qwen2.5-coder:7b
LOG_LEVEL=INFO
```

### Development Workflow
1. 每完成一个 Task，运行测试确保没有破坏现有功能
2. Commit 并 push 到 GitHub
3. 继续下一个 Task
4. 所有 Task 完成后，进行完整的 Phase 1 验收测试
