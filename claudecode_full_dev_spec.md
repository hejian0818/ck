# 单代码仓设计文档生成与代码问答系统
## Claude Code 一次性交付开发文档（Markdown）

> 本文档面向 Claude Code 直接执行开发。
> 目标是让开发代理在不反复追问需求的前提下，按本文档完成系统骨架、核心模块、接口、数据结构、状态机、策略阈值与验收能力。
> 项目类型：单代码仓分析系统。
> 输出形式：后端服务 + 索引构建流水线 + 双 Agent 执行链 + Markdown/PlantUML 文档产物。

---

# 1. 项目目标与范围

## 1.1 项目目标
构建一个面向单代码仓的结构化理解系统，支持两条核心能力：

1. 设计文档自动生成
2. 围绕文件、类、方法、代码片段的交互式代码问答

系统必须先通过 cleanarch 将源码仓解析为统一语义图 graphcode.json，再围绕：
- 模块（module）
- 文件（file）
- 符号（symbol）
- 关系（relation）

构建主索引体系，并基于：
- 结构化索引
- 向量索引
- 关系图索引
- span 定位映射

完成检索增强、文档生成、代码问答与图文一致性审查。

## 1.2 非目标
以下内容不属于本期交付范围：
- 多仓统一分析
- 代码自动修改与回写
- LLM 直接全文阅读全仓源码生成总结
- 通用 IDE 插件化实现
- 多 Agent 自由协商式复杂规划
- 全量 block / statement 级别全仓索引
- 实时代码增量监听与秒级热更新

## 1.3 设计约束
1. 单仓分析
2. 主索引只围绕 module / file / symbol / relation 四类对象
3. 原始源码不作为主检索语料
4. 原始源码仅用于：
   - span 落锚
   - 代码证据挂接
5. 摘要不使用 LLM
6. 摘要通过：
   - 结构特征抽取
   - 规则打标签
   - 模板生成
7. 架构使用共享底座上的双 Agent
   - 文档生成 Agent
   - 代码问答 Agent
8. 在线问答采用：
   - 默认简单主路径
   - 按需增强
   - 可降级
9. 图生成采用 PlantUML
10. 图文审查默认优先走规则校验，不默认引入额外大模型串行调用

---

# 2. Claude Code 开发执行要求

## 2.1 开发代理执行原则
Claude Code 在执行开发时必须遵守：
1. 先搭骨架，再补策略
2. 先打通主路径，再做增强路径
3. 先保证可运行，再做复杂优化
4. 所有切换条件必须是显式代码逻辑
5. 所有核心对象必须有稳定 ID
6. 日志、配置、阈值必须可观测、可调
7. 阈值写入配置文件，不允许散落硬编码
8. 所有 API / 数据结构使用类型定义

## 2.2 开发交付物
Claude Code 最终需要产出：
1. 项目代码仓
2. 后端服务骨架
3. cleanarch 接入代码
4. graphcode.json 定义与样例
5. 索引构建流水线
6. 文档生成 Agent
7. 代码问答 Agent
8. 记忆管理模块
9. 上下文构造模块
10. 图文审查模块
11. API 接口
12. 单元测试
13. 最小可运行 Demo
14. README 和运行说明

---

# 3. 系统总体架构

## 3.1 分层结构
系统分为 6 层：

### L1 解析层
- 仓库扫描
- 多语言解析
- cleanarch

### L2 语义图层
- graphcode.json

### L3 索引层
- 模块索引
- 文件索引
- 符号索引
- 关系索引
- 关系图索引
- span 定位映射

### L4 公共能力层
- 规则摘要生成
- 编码模型向量化
- 检索器
- 关系扩展器
- 证据包组装器
- 上下文构造器
- 记忆管理器
- PlantUML 生成器
- Reviewer / Validator

### L5 Agent 层
- 文档生成 Agent
- 代码问答 Agent

### L6 应用层
- 设计文档生成接口
- 代码问答接口
- 会话管理接口

## 3.2 组件边界
### 只做解析的组件
- cleanarch

### 只做索引构建的组件
- IndexBuilder
- SummaryBuilder
- EmbeddingBuilder
- GraphIndexBuilder
- SpanMapBuilder

### 只做在线能力的组件
- AnchorResolver
- Retriever
- GraphExpander
- ContextBuilder
- MemoryManager
- DocumentAgent
- QAAgent

---

# 4. 技术栈建议

## 4.1 语言与服务框架
建议：
- Python 3.11+
- FastAPI
- Pydantic v2
- Uvicorn
- SQLAlchemy（可选）
- Redis（缓存，可选）
- SQLite / PostgreSQL（元数据存储）
- 本地文件系统 / 对象存储（产物存储）

## 4.2 向量能力
建议：
- FAISS / Milvus / pgvector（二选一）
- 初期优先 FAISS 本地化

编码模型：
- 建议选择通用检索向量模型（如 BGE 系列）
- 原因：输入是规则生成的技术摘要，不是原始长代码

## 4.3 图与可视化
- PlantUML
- Graphviz（可选，仅用于内部调试）

---

# 5. 代码仓组织建议

项目目录建议如下：

```text
repo-root/
  app/
    api/
      qa.py
      doc.py
      repo.py
      session.py
    core/
      config.py
      logging.py
      constants.py
      thresholds.py
    models/
      graph_objects.py
      anchor.py
      memory.py
      retrieval.py
      prompts.py
      api_models.py
    services/
      cleanarch/
        scanner.py
        parser_adapter.py
        graph_builder.py
      indexing/
        normalize.py
        relation_enricher.py
        summary_builder.py
        embedding_builder.py
        structured_index.py
        graph_index.py
        span_index.py
      retrieval/
        anchor_resolver.py
        retriever.py
        graph_expander.py
        ranker.py
        evidence_packager.py
      agents/
        document_agent.py
        qa_agent.py
      context/
        context_builder.py
      memory/
        memory_manager.py
      review/
        validator.py
      diagrams/
        plantuml_generator.py
    storage/
      repositories.py
      vector_store.py
      graph_store.py
      span_store.py
    tests/
      ...
  scripts/
    build_index.py
    run_demo.py
  data/
    ...
  README.md
```

---

# 6. 数据模型设计

## 6.1 graphcode.json 顶层结构

```json
{
  "repo_meta": {},
  "modules": [],
  "files": [],
  "symbols": [],
  "relations": [],
  "spans": []
}
```

## 6.2 模块对象

```json
{
  "id": "M_order",
  "name": "order-domain",
  "path": "src/order",
  "metadata": {}
}
```

字段：
- id
- name
- path
- metadata

## 6.3 文件对象

```json
{
  "id": "F_order_service",
  "name": "OrderService.java",
  "path": "src/order/service/OrderService.java",
  "module_id": "M_order",
  "language": "java",
  "start_line": 1,
  "end_line": 220
}
```

字段：
- id
- name
- path
- module_id
- language
- start_line
- end_line

## 6.4 符号对象

```json
{
  "id": "S_create_order",
  "name": "createOrder",
  "qualified_name": "OrderService.createOrder",
  "type": "method",
  "signature": "createOrder(OrderRequest req)",
  "file_id": "F_order_service",
  "module_id": "M_order",
  "start_line": 78,
  "end_line": 126,
  "visibility": "public",
  "doc": ""
}
```

字段：
- id
- name
- qualified_name
- type
- signature
- file_id
- module_id
- start_line
- end_line
- visibility
- doc

## 6.5 关系对象

```json
{
  "id": "R_001",
  "relation_type": "calls",
  "source_id": "S_controller_submit",
  "target_id": "S_create_order",
  "source_type": "method",
  "target_type": "method",
  "source_module_id": "M_api",
  "target_module_id": "M_order"
}
```

字段：
- id
- relation_type
- source_id
- target_id
- source_type
- target_type
- source_module_id
- target_module_id

## 6.6 span 记录

```json
{
  "file_path": "src/order/service/OrderService.java",
  "line_start": 78,
  "line_end": 126,
  "module_id": "M_order",
  "file_id": "F_order_service",
  "symbol_id": "S_create_order",
  "node_type": "method"
}
```

字段：
- file_path
- line_start
- line_end
- module_id
- file_id
- symbol_id
- node_type

---

# 7. cleanarch 详细开发要求

## 7.1 职责
cleanarch 仅负责：
1. 扫描代码仓
2. 解析源码
3. 统一抽取对象
4. 统一抽取关系
5. 输出 graphcode.json

不得负责：
- 问答
- 文档生成
- LLM 摘要
- 策略切换

## 7.2 子任务

### 7.2.1 仓库扫描器
输入：
- repo_path
- ignore patterns

输出：
- 文件列表
- 目录树

必须过滤：
- .git
- node_modules
- dist
- build
- target
- 二进制文件

### 7.2.2 多语言解析适配
初期至少预留适配：
- Spoon
- CDT
- Tree-sitter

可先提供接口骨架和 mock 适配层。

### 7.2.3 graph 构建器
必须把不同语言解析结果映射为统一对象模型。

要求：
- 所有对象有稳定 ID
- 所有 relation 使用 source_id / target_id
- 所有 symbol 带 line range
- 所有 file 带 module_id
- 所有 span 可反查 symbol/file/module

---

# 8. 索引编制详细要求

## 8.1 对象归一化
模块：
- name 标准化
- path 标准化

文件：
- path 相对仓库统一化
- name 与 path 分离

符号：
- qualified_name 规范化
- signature 规范化
- symbol_type 规范化

关系：
- relation_type 统一枚举
- source/target 对象必须存在

## 8.2 关系补全
必须额外构造：
- reverse callers
- reverse references
- module depends_on module
- file depends_on file

要求：
- 关系图索引可一跳、反向一跳查询
- 后续可支持二跳扩展

## 8.3 规则摘要生成
不使用 LLM，全部走规则。

### 模块摘要生成
至少包含：
- 模块路径
- 模块职责标签
- 核心文件
- 核心符号
- 相邻模块

### 文件摘要生成
至少包含：
- 文件路径
- 所属模块
- 文件职责标签
- 主要符号
- 依赖对象

### 符号摘要生成
至少包含：
- 名称 / 签名
- 所属文件 / 模块
- 参数 / 返回值
- 职责标签
- caller/callee
- 外部依赖

### 关系摘要生成
至少包含：
- relation_type
- source
- target
- source/target 所属模块
- 关系标签

## 8.4 索引层实现要求

### 8.4.1 结构化索引
必须支持：
- by id
- by name
- by path
- by qualified_name
- by file_id / module_id

### 8.4.2 向量索引
必须按对象类型分桶：
- module
- file
- symbol
- relation

### 8.4.3 关系图索引
必须支持：
- 邻接查询
- 反向邻接查询
- 一跳扩展
- 二跳扩展（可选）

### 8.4.4 span 定位映射
必须支持：
- file_path + line range → symbol/file/module
- symbol_id → file_path + line range

---

# 9. 锚点系统开发要求

## 9.1 锚点定义
锚点是当前问题在代码仓中的结构化定位中心。

允许四种层级：
- module
- file
- symbol
- none

建议 Python 模型：

```python
from dataclasses import dataclass
from typing import Optional, Literal

AnchorLevel = Literal["module", "file", "symbol", "none"]
AnchorSource = Literal[
    "explicit_span",
    "explicit_file",
    "explicit_module",
    "name_match",
    "memory_inherit",
    "retrieval_infer",
    "none"
]

@dataclass
class Anchor:
    level: AnchorLevel
    source: AnchorSource
    confidence: float
    module_id: Optional[str] = None
    file_id: Optional[str] = None
    symbol_id: Optional[str] = None
    file_path: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
```

## 9.2 锚点确定优先级
严格按以下顺序：
1. 用户显式选择代码片段 / 文件 / 模块
2. 问题中的明确对象名
3. 上轮锚点继承
4. 无锚点首轮检索后反推
5. none

## 9.3 span 落锚规则
如果用户输入：
- file_path
- line_start
- line_end

则必须：
1. 先缩到当前 file 的 span 列表
2. 找所有覆盖当前片段的对象
3. 优先返回最小包围区间对象
4. 优先级：
   - method/function
   - class/interface
   - file

## 9.4 名称命中锚点规则
问题中如果命中：
- 模块名
- 文件名
- 方法名
- 类名

则走结构化索引高置信匹配。

匹配必须处理：
- 唯一命中
- 轻度歧义
- 多命中失败

## 9.5 锚点继承规则
只有满足下列条件才允许继承：
1. 上轮锚点存在
2. 当前问题明显是追问
3. 当前会话未明显切题

## 9.6 无锚点反推
如果前 3 步都失败，则：
1. 先无锚点初始检索
2. 统计 top-k 集中度
3. 若结果在某个 symbol/file/module 上明显集中，则形成弱锚点
4. 否则保持 none

---

# 10. 代码问答 Agent 详细开发要求

## 10.1 主链路
必须实现固定流程：
1. 确定锚点
2. 读取记忆
3. 范围收缩
4. 首轮召回
5. 关系扩展
6. 候选融合与重排
7. 证据包组装
8. 上下文裁剪
9. 生成回答
10. 回写记忆

## 10.2 范围收缩规则
### symbol 锚点
范围：
- 当前 symbol
- 当前 file
- 当前 module

### file 锚点
范围：
- 当前 file
- 当前 module

### module 锚点
范围：
- 当前 module
- 邻接模块

### none
不做强范围限制，走无锚点检索

## 10.3 首轮召回
### 结构化召回
必须先拿：
- 当前对象本体
- 当前对象直接相关对象
- 名称命中对象

### 向量召回
根据当前层级和问题内容补充：
- module vectors
- file vectors
- symbol vectors
- relation vectors

向量召回不能替代结构化召回。

## 10.4 关系扩展
至少支持：
- callers
- callees
- depends_on
- reverse depends_on
- reverse references

默认只扩一跳。
二跳扩展必须满足阈值条件。

## 10.5 候选融合与重排
排序必须结合：
- 锚点接近度
- 名称命中度
- 对象类型匹配度
- 语义相似度
- 图距离
- 记忆加权

输出 top-k 统一候选簇。

## 10.6 证据包固定格式
必须统一输出为：
1. 当前问题
2. 当前代码片段
3. 当前锚点说明
4. 局部结构说明
5. 局部关系说明
6. 当前会话状态摘要

此结构供 Context Builder 使用。

---

# 11. 文档生成 Agent 详细开发要求

## 11.1 文档生成原则
文档生成必须是章节级检索增强，禁止整篇大 prompt 直接生成。

## 11.2 章节骨架
至少包含以下章节：
1. 模块划分
2. 模块职责
3. 核心流程
4. 关键类与接口
5. 依赖关系说明

## 11.3 章节检索路由
### 模块职责
检索：
- module index
- file index
- module depends_on

### 核心流程
检索：
- relation index
- symbol index
- 局部主链路

### 关键类与接口
检索：
- symbol index
- file index
- extends / implements

### 依赖关系
检索：
- relation index
- module/file dependency graph

## 11.4 PlantUML 生成
PlantUML 图必须基于真实结构对象和关系对象生成。

允许的图：
- 模块图
- 类图
- 依赖图
- 关系图

不得让 LLM 自由虚构图结构。

## 11.5 文档装配
最终装配必须输出：
- 章节正文
- 图
- 图说明
- 术语表（可选）

---

# 12. 上下文工程开发要求

## 12.1 目标
上下文工程不堆聊天历史，而是围绕当前锚点组织本轮 prompt。

## 12.2 Context Builder 输入
- 当前问题
- 当前代码片段（可选）
- 当前锚点
- 检索结果
- 记忆状态

## 12.3 Context Builder 输出
必须输出结构化上下文：
1. 当前问题
2. 当前代码片段
3. 当前锚点说明
4. 局部结构说明
5. 局部关系说明
6. 会话状态摘要
7. 回答要求

## 12.4 Token 预算规则
优先保留：
1. 当前代码片段
2. 当前锚点摘要
3. 一跳关键关系
4. 当前 file/class/module 摘要
5. 上轮局部子图摘要
6. 二跳对象

超限时按上述顺序裁剪。

---

# 13. 记忆管理开发要求

## 13.1 记忆模型
只允许四类记忆：

### Anchor Memory
保存：
- current_anchor

### Retrieval Memory
保存：
- recent_object_ids
- recent_subgraph_summary
- recent_evidence_summary

### Focus Memory
保存：
- current_focus

### Task Memory
保存：
- current_section
- generated_sections
- generated_diagrams
- terminology

## 13.2 更新规则
### Anchor Memory
- 新选择出现时覆盖
- 锚点为 none 时不覆盖强锚点（除非显式清空）

### Retrieval Memory
- 用最新局部子图覆盖旧子图
- 锚点变化过大时清空旧子图

### Focus Memory
- 主题延续则保留
- 主题切换则覆盖或衰减

### Task Memory
- 文档生成阶段更新
- 与 QA 会话状态隔离

---

# 14. 策略切换与量化阈值

## 14.1 每轮必须计算的五个指标
### A：锚点置信度
### C：首轮召回集中度
### E：证据充分度
### G：扩展收益
### R：结果一致性

## 14.2 建议阈值
### A
- 强锚点：A >= 0.80
- 弱锚点：0.60 <= A < 0.80
- 放弃锚点：A < 0.60

### C
- 可反推：C >= 0.55
- 可增强：C >= 0.45
- 发散：C < 0.35

### E
- 直接回答：E >= 0.60
- 增强：0.40 <= E < 0.60
- 降级：E < 0.40

### G
- 保留扩展：G >= 0.35
- 停止扩展：G < 0.25

### R
- 可继续整合：R >= 0.55
- 发散：R < 0.40

## 14.3 四状态状态机
### S1 默认路径
条件：
- A >= 0.80
- E >= 0.60

执行：
- 当前对象 + 一跳关系
- 直接回答

### S2 增强路径
条件：
- A >= 0.60
- E < 0.60
- C >= 0.45

执行：
- 补向量召回
- 补关系扩展
- 必要时二跳

### S3 反推路径
条件：
- A < 0.60
- 无锚点首轮检索后 C >= 0.55

执行：
- 反推弱锚点
- 再做局部证据补足

### S4 降级路径
触发任一：
- A < 0.40
- C < 0.35
- E < 0.40
- R < 0.40
- G < 0.25

执行：
- 多中心回答
- 局部可确认回答
- 要求补充上下文

---

# 15. 图文审查开发要求

## 15.1 默认路径
默认只做规则校验，不额外串大模型。

## 15.2 规则校验必须覆盖
1. 对象存在性
2. 关系可回溯性
3. 图节点边合法性
4. 图文对齐
5. 术语一致性

## 15.3 审查结果分级
- pass
- minor_issue
- major_issue

### minor_issue
可直接局部修文。

### major_issue
必须回退：
- 补检索
- 局部重写
- 图说明修正

---

# 16. API 设计

## 16.1 建库接口
POST /repo/build-index

### Request
```json
{
  "repo_path": "/path/to/repo",
  "branch": "main"
}
```

### Response
```json
{
  "build_id": "build_001",
  "status": "running"
}
```

## 16.2 代码问答接口
POST /qa/ask

### Request
```json
{
  "repo_id": "repo_001",
  "session_id": "sess_001",
  "question": "这里为什么不直接失败，而是先挂起任务？",
  "selection": {
    "file_path": "src/task/service/TaskRetryService.java",
    "line_start": 85,
    "line_end": 96
  }
}
```

### Response
```json
{
  "answer": "...",
  "anchor": {
    "level": "symbol",
    "symbol_id": "S_handle_failure"
  },
  "confidence": 0.84,
  "used_objects": ["S_handle_failure", "F_task_retry_service"],
  "need_more_context": false
}
```

## 16.3 文档生成接口
POST /doc/generate

### Request
```json
{
  "repo_id": "repo_001",
  "document_type": "design_doc"
}
```

### Response
```json
{
  "doc_task_id": "doc_001",
  "status": "running"
}
```

## 16.4 会话管理接口
- GET /qa/session/{session_id}
- POST /qa/session/{session_id}/reset

---

# 17. 性能与缓存要求

## 17.1 span 定位优化
大型仓下 span 定位必须：
1. 按 file_id / file_path 分桶
2. 文件内按 start_line 排序
3. 采用二分 + 局部扫描
4. 热点文件做缓存
5. 最近命中的 anchor 做 session 级缓存

## 17.2 检索缓存
必须支持：
- session 级最近局部子图缓存
- 对象摘要缓存
- 向量查询缓存（可选）

## 17.3 文档生成缓存
建议缓存：
- 已生成章节
- 已生成 PlantUML 图
- 已通过审查的章节状态

---

# 18. 日志与可观测性要求

必须为以下关键节点加日志：
1. 锚点来源与置信度
2. 检索范围
3. 首轮召回 top-k
4. 关系扩展结果数
5. A/C/E/G/R 五个指标
6. 状态机状态
7. 是否触发降级
8. 最终 used_objects
9. 文档章节生成耗时
10. 图文审查结果

日志建议使用 JSON 结构。

---

# 19. 开发阶段拆解

## Phase 1：底座版（必须先做）
目标：跑通主链路最小闭环。

### 交付内容
- cleanarch
- graphcode.json
- module/file/symbol/relation 索引
- 关系图索引
- span 定位映射
- 显式锚点
- 一跳关系扩展
- 基础 QA 接口
- Anchor Memory
- Context Builder 基础版

### 验收
- 用户选代码片段后能正确落锚
- 能回答“这个方法做什么 / 谁调用它 / 属于哪个模块”

## Phase 2：增强版
目标：支持复杂一点的问答和追问。

### 交付内容
- 规则摘要
- 向量索引
- 名称匹配锚点
- 锚点继承
- 重排
- 检索记忆 / 焦点记忆
- 指标计算（A/C/E/G/R）
- 状态机
- 降级基础版

### 验收
- 支持追问
- 支持“为什么这样设计”“谁依赖它”“影响范围”这类增强问题
- 锚点不清时不乱答

## Phase 3：文档生成版
目标：打通设计文档自动生成全链路。

### 交付内容
- 文档骨架规划
- 章节级检索
- 章节生成
- PlantUML 图生成
- 图文审查
- 任务记忆

### 验收
- 能产出完整设计文档
- 能附带模块图/类图/关系图
- 图文一致性检查有效

## Phase 4：工程完善版
目标：提升鲁棒性和可维护性。

### 交付内容
- 更完整降级模式
- 更细日志与指标
- 缓存优化
- 配置中心
- Demo / README / 测试补齐

---

# 20. 测试与验收

## 20.1 必测用例
### cleanarch
- 小仓解析
- 中仓解析
- 多文件解析
- 关系抽取正确性

### 锚点系统
- 代码片段落锚
- 文件落锚
- 模块落锚
- 名称匹配落锚
- 继承锚点
- 锚点失败降级

### 检索系统
- 当前对象本体召回
- 一跳 caller/callee
- depends_on / reverse depends_on
- 向量补召回
- 重排效果

### QA
- 单轮问答
- 多轮追问
- 锚点切换
- 降级回答
- 请求补充上下文

### 文档生成
- 大纲
- 章节生成
- 图生成
- 图文审查
- 文档装配

## 20.2 最低验收标准
1. 单仓可建库
2. 用户可通过代码片段稳定问答
3. 支持至少一跳关系扩展
4. 支持多轮追问
5. 能生成基础设计文档
6. 锚点不清时不会胡乱高置信回答
7. 所有核心模块有测试和日志

---

# 21. Claude Code 执行注意事项

1. 不要一开始就实现所有增强策略
2. 第一版必须优先保证主路径可运行
3. 二跳扩展、无锚点反推、多中心模式都应在主路径稳定后追加
4. 所有阈值放在配置文件中
5. 所有模块之间通过类型化模型交互
6. 不允许在核心链路里塞大量临时 if-else 魔法判断
7. 不允许省略日志与失败分支
8. 不允许把聊天原文直接当记忆主体

---

# 22. 最终一句话开发指令（给 Claude Code）

请基于本开发文档，按以下优先级实现系统：

1. 先完成 cleanarch -> graphcode.json -> 四层索引 -> span 定位 -> 基础 QA 主闭环
2. 再完成规则摘要、向量索引、增强检索和记忆管理
3. 最后完成文档生成 Agent、PlantUML 图生成和图文审查

要求所有核心逻辑具备：
- 稳定 ID
- 类型定义
- 日志
- 配置阈值
- 失败降级能力

禁止一开始实现过度复杂版本；必须先交付可跑通、可测试、可扩展的主路径。
