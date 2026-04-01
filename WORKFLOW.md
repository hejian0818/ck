# Phase 2 并行开发工作流

## 角色分工

### 项目经理（Claude）
- 分配任务给各个工程师
- 创建和管理分支
- 审核代码质量
- 运行测试验证
- 合并分支到 main
- 处理冲突

### 工程师（Codex）
- Engineer A: 负责 Track 1（规则摘要生成）
- Engineer B: 负责 Track 2（向量索引）
- Engineer C: 负责 Track 3（增强检索）
- Engineer D: 负责 Track 4（记忆与状态机）

## 开发流程

### 阶段 1: Track 1 & Track 2（并行）

#### Engineer A 工作流
1. 项目经理创建分支 `feature/phase2-track1-summary`
2. Engineer A 在该分支开发
3. 完成后提交到自己的分支
4. 通知项目经理审核

#### Engineer B 工作流
1. 项目经理创建分支 `feature/phase2-track2-vector`
2. Engineer B 在该分支开发
3. 完成后提交到自己的分支
4. 通知项目经理审核

#### 项目经理审核流程
1. 切换到工程师分支
2. 检查代码质量：
   - 类型注解完整
   - 日志记录充分
   - 错误处理完善
   - 符合项目规范
3. 运行测试：
   - `uv run pytest app/tests/`
   - 检查新增功能是否工作
4. 审核通过：
   - 合并到 main
   - Push 到 GitHub
   - 通知工程师
5. 审核不通过：
   - 提出修改意见
   - 工程师修复后重新提交

### 阶段 2: Track 3 & Track 4（并行）
等 Track 1 & 2 合并后，启动 Track 3 & 4，流程同上。

## 分支命名规范
- `feature/phase2-track1-summary` - 规则摘要生成
- `feature/phase2-track2-vector` - 向量索引
- `feature/phase2-track3-retrieval` - 增强检索
- `feature/phase2-track4-memory` - 记忆与状态机

## 审核检查清单

### 代码质量
- [ ] 所有函数有类型注解
- [ ] 所有类有 docstring
- [ ] 变量命名清晰
- [ ] 没有硬编码魔法数字
- [ ] 错误处理完善

### 功能完整性
- [ ] 所有任务点已实现
- [ ] 集成到现有流程
- [ ] 数据库 schema 更新
- [ ] API 接口正常

### 测试覆盖
- [ ] 有单元测试
- [ ] 测试通过
- [ ] 边界情况覆盖

### 文档
- [ ] README 更新（如需要）
- [ ] 代码注释充分
- [ ] Commit message 清晰

## Git 操作命令

### 创建分支
```bash
git checkout -b feature/phase2-track1-summary
git push -u origin feature/phase2-track1-summary
```

### 审核分支
```bash
git fetch origin
git checkout feature/phase2-track1-summary
# 审核代码
uv run pytest app/tests/
```

### 合并分支
```bash
git checkout main
git merge feature/phase2-track1-summary
git push origin main
git branch -d feature/phase2-track1-summary
git push origin --delete feature/phase2-track1-summary
```

## 冲突处理策略
1. Track 1 & 2 修改不同模块，冲突概率低
2. Track 3 & 4 等 1 & 2 合并后再启动
3. 如有冲突，项目经理手动解决
