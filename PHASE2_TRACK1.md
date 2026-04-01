# Phase 2 - Track 1: 规则摘要生成

## 目标
为所有对象（Module/File/Symbol/Relation）生成规则摘要，不使用 LLM。

## 负责模块
- `app/services/indexing/summary_builder.py`

## 任务清单

### Task 1: ModuleSummaryBuilder
实现模块摘要生成器。

**输入:** Module 对象 + 关联的 File/Symbol 列表

**输出摘要包含:**
- 模块路径
- 模块职责标签（根据路径推断：api/service/model/util 等）
- 核心文件列表（top 5）
- 核心符号列表（public 类/函数，top 10）
- 相邻模块（通过 relation 的 source_module_id/target_module_id）

**实现要点:**
- 职责标签规则：
  - 包含 "api"/"controller" -> "API Layer"
  - 包含 "service"/"business" -> "Business Logic"
  - 包含 "model"/"entity" -> "Data Model"
  - 包含 "util"/"helper" -> "Utility"
  - 默认 -> "Module"
- 核心文件：按符号数量排序
- 核心符号：只取 public 的 class/function

**Commit:** `feat(indexing): implement module summary builder`

---

### Task 2: FileSummaryBuilder
实现文件摘要生成器。

**输入:** File 对象 + 关联的 Symbol 列表 + 关联的 Relation 列表

**输出摘要包含:**
- 文件路径
- 所属模块
- 文件职责标签（根据文件名推断）
- 主要符号列表（所有 public 符号）
- 依赖对象（通过 relation 找到的外部 file/symbol）

**实现要点:**
- 职责标签规则：
  - 文件名包含 "test" -> "Test"
  - 文件名包含 "config" -> "Configuration"
  - 文件名包含 "main"/"app" -> "Entry Point"
  - 默认 -> 根据语言（"Python Module"/"Java Class" 等）
- 依赖对象：只统计跨文件的依赖

**Commit:** `feat(indexing): implement file summary builder`

---

### Task 3: SymbolSummaryBuilder
实现符号摘要生成器。

**输入:** Symbol 对象 + 关联的 Relation 列表

**输出摘要包含:**
- 名称 / 签名
- 所属文件 / 模块
- 参数 / 返回值（从 signature 解析）
- 职责标签（根据名称推断）
- caller/callee 列表（通过 relation）
- 外部依赖（跨模块的调用）

**实现要点:**
- 职责标签规则：
  - 名称包含 "get"/"find"/"query" -> "Query"
  - 名称包含 "create"/"add"/"insert" -> "Create"
  - 名称包含 "update"/"modify" -> "Update"
  - 名称包含 "delete"/"remove" -> "Delete"
  - 名称包含 "validate"/"check" -> "Validation"
  - 默认 -> symbol.type（"Method"/"Function"/"Class"）
- 参数/返回值：简单正则解析 signature

**Commit:** `feat(indexing): implement symbol summary builder`

---

### Task 4: RelationSummaryBuilder
实现关系摘要生成器。

**输入:** Relation 对象 + source/target 对象

**输出摘要包含:**
- relation_type
- source 名称和类型
- target 名称和类型
- source/target 所属模块
- 关系标签（描述性文本）

**实现要点:**
- 关系标签模板：
  - calls: "{source} calls {target}"
  - extends: "{source} extends {target}"
  - implements: "{source} implements {target}"
  - depends_on: "{source} depends on {target}"
  - references: "{source} references {target}"

**Commit:** `feat(indexing): implement relation summary builder`

---

### Task 5: 集成到索引构建流程
修改 `app/services/cleanarch/graph_builder.py`，在构建完 GraphCode 后自动生成摘要。

**修改点:**
1. 在 `build_graph()` 方法最后调用摘要生成
2. 将摘要存储到数据库（新增 summaries 表或在现有表加 summary 字段）
3. 更新 `app/storage/repositories.py` 支持摘要的 CRUD

**数据库 schema 更新:**
```sql
ALTER TABLE modules ADD COLUMN summary TEXT;
ALTER TABLE files ADD COLUMN summary TEXT;
ALTER TABLE symbols ADD COLUMN summary TEXT;
ALTER TABLE relations ADD COLUMN summary TEXT;
```

**Commit:** `feat(indexing): integrate summary generation into build pipeline`

---

## 验收标准
1. ✅ 可以为测试仓库的所有对象生成摘要
2. ✅ 摘要包含所有必需字段
3. ✅ 摘要存储到数据库
4. ✅ 可以通过 API 查询摘要
5. ✅ 有单元测试覆盖各个 Builder

## 技术要求
- 所有 Builder 使用统一接口
- 摘要生成纯规则，不调用 LLM
- 所有标签规则可配置（写在 config 或常量文件）
- 日志记录摘要生成耗时
