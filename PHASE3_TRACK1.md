# Phase 3 - Track 1: 文档骨架规划与段落检索

## 目标
实现文档骨架自动规划和段落级检索，为设计文档生成提供结构和内容基础。

## 负责模块
- `app/services/agents/doc_agent.py`（新增）
- `app/services/retrieval/doc_retriever.py`（新增）
- `app/models/doc_models.py`（新增）
- `app/api/doc.py`（新增）

## 任务清单

### Task 1: 文档模型定义
新增 `app/models/doc_models.py`，定义文档相关数据结构。

**模型：**
```python
class DocumentSkeleton(BaseModel):
    """文档骨架，描述文档的层级结构。"""
    repo_id: str
    title: str
    sections: list[SectionPlan]

class SectionPlan(BaseModel):
    """段落规划。"""
    section_id: str
    title: str
    level: int  # 1=一级标题, 2=二级标题, ...
    section_type: Literal["overview", "architecture", "module", "api", "data_flow", "dependency", "summary"]
    target_object_ids: list[str]  # 该段落需要检索的对象ID
    description: str  # 该段落应包含的内容描述

class SectionContent(BaseModel):
    """生成的段落内容。"""
    section_id: str
    title: str
    content: str  # Markdown 格式
    diagrams: list[str]  # PlantUML 代码列表
    used_objects: list[str]
    confidence: float

class DocumentResult(BaseModel):
    """完整文档生成结果。"""
    repo_id: str
    title: str
    sections: list[SectionContent]
    metadata: dict[str, Any]
```

**Commit:** `feat(doc): define document generation models`

### Task 2: 文档骨架规划器
新增骨架规划逻辑，根据 GraphCode 结构自动生成文档骨架。

**规划规则：**
1. 固定段落：概述、架构总览、总结
2. 每个模块生成一个模块段落（二级标题）
3. 模块内重要文件生成子段落（三级标题）
4. 如有跨模块依赖关系，生成依赖分析段落
5. 如有 API 相关符号（路由、控制器），生成 API 段落

**入口：**
```python
class SkeletonPlanner:
    def plan(self, repo_id: str) -> DocumentSkeleton:
        """根据仓库图结构自动生成文档骨架。"""
```

**Commit:** `feat(doc): implement document skeleton planner`

### Task 3: 段落级检索器
新增 `app/services/retrieval/doc_retriever.py`，为每个段落检索所需上下文。

**逻辑：**
1. 根据 SectionPlan.target_object_ids 检索关联对象
2. 根据 SectionPlan.section_type 决定检索深度：
   - overview: 全局模块列表 + 各模块摘要
   - module: 模块内全部文件和关键符号
   - api: API 相关符号 + 调用链
   - data_flow: 关系链（depends_on, calls）
   - dependency: 跨模块关系
3. 用向量召回补充语义相关内容
4. 复用 Ranker 排序

**Commit:** `feat(doc): implement section-level retrieval for document generation`

### Task 4: 文档 API 端点
新增 `app/api/doc.py`，提供文档生成 API。

**端点：**
- `POST /doc/plan` → 返回 DocumentSkeleton
- `POST /doc/generate` → 返回 DocumentResult
- `GET /doc/{repo_id}/sections` → 返回段落列表

**请求模型：**
```python
class DocPlanRequest(BaseModel):
    repo_id: str

class DocGenerateRequest(BaseModel):
    repo_id: str
    skeleton: DocumentSkeleton | None = None  # 可选自定义骨架
```

**Commit:** `feat(doc): add document generation API endpoints`

### Task 5: 测试
- 骨架规划测试（至少测试固定段落 + 模块段落生成）
- 段落检索测试
- API 端点测试

**Commit:** `test: add tests for document skeleton planner and section retrieval`

## 验收标准
1. 能根据仓库结构自动生成合理的文档骨架
2. 每个段落能检索到对应的代码对象和关系
3. API 端点正常工作
4. 有单元测试覆盖
