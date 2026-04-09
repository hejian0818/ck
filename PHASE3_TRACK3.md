# Phase 3 - Track 3: 文档审查与任务记忆

## 目标
实现文档与图表的一致性审查，以及文档生成过程中的任务记忆管理。

## 负责模块
- `app/services/review/doc_reviewer.py`（新增）
- `app/services/memory/memory_manager.py`（扩展 Task Memory）
- `app/services/agents/doc_agent.py`（扩展审查集成）

## 前置依赖
- Phase 3 Track 1 + Track 2

## 任务清单

### Task 1: 文档审查器
新增 `app/services/review/doc_reviewer.py`，实现文档一致性检查。

**审查维度：**
1. **结构完整性：**
   - 骨架中的所有段落都已生成
   - 标题层级连续（无跳级）
   - 有概述和总结段落

2. **内容一致性：**
   - 段落中提及的对象确实存在于图中
   - 图表中的模块/类与段落描述匹配
   - 跨段落引用一致（如模块 A 在概述和详情中描述一致）

3. **图文一致性：**
   - 模块依赖图中的模块与文档中描述的模块一致
   - 类关系图中的类与代码中实际存在的类一致
   - 调用流程图中的方法签名正确

**输出：**
```python
class ReviewResult(BaseModel):
    passed: bool
    issues: list[ReviewIssue]

class ReviewIssue(BaseModel):
    severity: Literal["error", "warning", "info"]
    section_id: str | None
    category: Literal["structure", "content", "diagram"]
    message: str
```

**Commit:** `feat(review): implement document consistency reviewer`

### Task 2: 任务记忆
扩展 `memory_manager.py`，增加 Task Memory 支持。

**Task Memory 数据结构：**
```python
class TaskMemory(BaseModel):
    task_type: Literal["doc_generation", "qa"]
    repo_id: str
    progress: dict[str, str]  # section_id -> status ("pending"/"done"/"failed")
    generated_sections: list[str]  # 已生成的 section_id 列表
    retry_count: dict[str, int]  # section_id -> 重试次数
    started_at: str
    last_updated_at: str
```

**管理逻辑：**
- 文档生成开始时创建 Task Memory
- 每个段落生成完成后更新进度
- 支持断点续传：如果任务中断，可以从 Task Memory 恢复进度
- 重试超过 3 次的段落标记为 failed

**Commit:** `feat(memory): implement task memory for document generation progress`

### Task 3: 审查集成
将审查器集成到文档生成流程。

**流程：**
1. 文档生成完成后自动运行审查
2. error 级别问题触发自动修复尝试：
   - 缺失段落 → 重新生成
   - 对象引用不存在 → 从文本中移除引用
   - 图表错误 → 重新生成图表
3. warning 级别问题记录到 DocumentResult.metadata
4. 审查结果附加到最终文档

**Commit:** `feat(doc): integrate reviewer into document generation pipeline`

### Task 4: 完善 DocAgent
完善 `doc_agent.py`，实现完整的文档生成协调流程。

**完整流程：**
1. 创建 Task Memory
2. 生成/接收文档骨架
3. 逐段落检索 + 生成
4. 生成图表
5. 运行一致性审查
6. 自动修复 error 级别问题
7. 组装最终文档
8. 更新 Task Memory 为完成

**日志要求：**
```json
{
  "repo_id": "...",
  "task_type": "doc_generation",
  "total_sections": 8,
  "generated_sections": 8,
  "failed_sections": 0,
  "diagrams_generated": 3,
  "review_issues": {"error": 0, "warning": 2, "info": 1},
  "elapsed_ms": 15000
}
```

**Commit:** `feat(doc): complete document agent with full generation pipeline`

### Task 5: 测试
- 审查器测试（各审查维度）
- Task Memory 测试（创建、更新、恢复）
- 端到端集成测试

**Commit:** `test: add tests for document reviewer and task memory`

## 验收标准
1. 审查器能检测结构、内容、图文不一致
2. 自动修复能处理常见 error 级别问题
3. Task Memory 正确跟踪生成进度
4. 断点续传功能正常
5. 有单元测试覆盖
