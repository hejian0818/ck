# 多 Agent 并行开发计划

## Phase 2 任务拆分（4个并行轨道）

### Track 1: 规则摘要生成 (Agent A + Codex)
**负责模块:** `app/services/indexing/summary_builder.py`

**任务:**
1. 实现 ModuleSummaryBuilder
2. 实现 FileSummaryBuilder
3. 实现 SymbolSummaryBuilder
4. 实现 RelationSummaryBuilder
5. 集成到索引构建流程

**验收:** 可以为所有对象生成规则摘要

---

### Track 2: 向量索引 (Agent B + Codex)
**负责模块:** `app/services/indexing/embedding_builder.py`, `app/storage/vector_store.py`

**任务:**
1. 配置 pgvector 表结构
2. 实现 EmbeddingBuilder（调用编码模型）
3. 实现 VectorStore（CRUD + 相似度搜索）
4. 按对象类型分桶存储
5. 集成到索引构建流程

**验收:** 可以向量化摘要并检索

---

### Track 3: 增强检索与排序 (Agent C + Codex)
**负责模块:** `app/services/retrieval/`

**任务:**
1. 实现名称匹配锚点（name_match）
2. 实现锚点继承（memory_inherit）
3. 增强 Retriever 支持向量召回
4. 实现 Ranker（融合结构化+向量结果）
5. 实现关系扩展（二跳）

**验收:** 支持无显式选择的问答

---

### Track 4: 记忆与状态机 (Agent D + Codex)
**负责模块:** `app/services/memory/`, `app/services/agents/qa_agent.py`

**任务:**
1. 扩展 MemoryManager（Retrieval Memory + Focus Memory）
2. 实现指标计算（A/C/E/G/R）
3. 实现四状态状态机（S1/S2/S3/S4）
4. 实现降级处理逻辑
5. 更新 QAAgent 集成状态机

**验收:** QA 可以根据指标自动切换策略

---

## 执行方式

### 启动 4 个 Codex 任务
```bash
# Track 1
codex task "实现 PARALLEL_DEV_PLAN.md 中的 Track 1: 规则摘要生成。读取 CLAUDE.md 了解架构，严格按照 Phase 2 要求实现。每完成一个子任务就 commit + push。"

# Track 2
codex task "实现 PARALLEL_DEV_PLAN.md 中的 Track 2: 向量索引。读取 CLAUDE.md 了解架构，使用 pgvector。每完成一个子任务就 commit + push。"

# Track 3
codex task "实现 PARALLEL_DEV_PLAN.md 中的 Track 3: 增强检索与排序。读取 CLAUDE.md 了解架构，扩展现有 retrieval 模块。每完成一个子任务就 commit + push。"

# Track 4
codex task "实现 PARALLEL_DEV_PLAN.md 中的 Track 4: 记忆与状态机。读取 CLAUDE.md 了解架构，实现指标和状态机。每完成一个子任务就 commit + push。"
```

### 监控脚本（每 3 分钟检查）
```bash
/loop 3m "检查所有 Codex 任务进度，汇总各 Track 完成情况"
```

---

## 冲突处理策略

### 可能的冲突点
1. `app/services/indexing/` - Track 1 和 Track 2 都会修改
2. `app/services/retrieval/retriever.py` - Track 3 会大幅修改
3. `app/services/agents/qa_agent.py` - Track 4 会重构

### 解决方案
1. **Track 1 和 2 先行** - 它们修改的是索引构建（离线），冲突少
2. **Track 3 和 4 后行** - 等 Track 1/2 完成后再启动，避免同时改 QA 流程
3. **使用 Git worktree** - 每个 Track 在独立 worktree 开发，最后合并

---

## 时间估算

- Track 1: ~20 分钟（规则生成相对简单）
- Track 2: ~30 分钟（需要配置 pgvector + 编码模型）
- Track 3: ~25 分钟（扩展现有检索逻辑）
- Track 4: ~35 分钟（状态机逻辑复杂）

**串行总时间:** ~110 分钟
**并行总时间:** ~35 分钟（最长的 Track 4）

**加速比:** 3.1x

---

## 验收检查点

### 中期检查（15 分钟后）
- Track 1: 至少完成 Module + File 摘要
- Track 2: pgvector 表结构就绪
- Track 3: 名称匹配锚点完成
- Track 4: 指标计算完成

### 最终验收
- 所有 Track 代码已合并到 main
- 通过 Phase 2 集成测试
- 可以回答复杂问答（无显式选择、追问、降级）
