# 防不同步流程改进方案

> 第一周暴露的问题：有已完成工作未被 tracking 文档记录，commit 后才补同步。

---

## 🔍 根因分析

本次不同步的 4 种具体表现：

| # | 现象 | 根因 | 涉及文件 |
|---|------|------|---------|
| 1 | commit `08416ec` 完成了 2.1.9（T0 词典+标签库），但 task-plan.md 仍标记 ⏳ | 完成工作后忘同步 task-plan | `docs/task-plan.md` |
| 2 | Day 6 的 3 处修复 + 前端检验无 tracking 条目 | 修复后忘写 progress.md | `progress.md` |
| 3 | Day 6 修复记录未写入 change-log | 同上 | `docs/change-log.md` |
| 4 | 前端检验脚本生成的 32 张截图未纳入版本管理 | 测试产出物无提交纪律 | `docs/screenshots/` |

**共同模式：** 完成工作 → `git commit` → **忘同步 tracking 文档**。没有强制检查点。

---

## ✅ 改进方案

### 方案 A：CLAUDE.md 追加跟踪纪律（推荐）

在现有 `✅ 验证阶段` 节末尾追加 3 条规则：

| # | 规则 | 说明 |
|---|------|------|
| **V10** | **Commit 前三角稽核** | commit 前同时检查 progress.md / task-plan.md / change-log.md 是否与本次变更对应。新增代码 → change-log 有记录；任务完成 → task-plan 状态更新；当天工作 → progress 有总结。**三件缺一不得 commit** |
| **V11** | **截图产物随 script 提交** | `docs/screenshots/` 下的测试截图视为正式文档，检验脚本运行后 `git status` 检查未跟踪截图，批量 git add |
| **V12** | **commit 标题含 Day 号** | `Day X: <核心变更>` 格式（如 `Day 6: T0 词典 + 前端检验`），便于快速匹配 task-plan 日期 |

### 方案 B：.claude/commit_checklist.md 模板

每次 commit 前快速核对：

```markdown
# Commit 前核对
□ progress.md 已更新本条
□ task-plan.md 对应任务状态 ✅
□ change-log.md 已记录变更
□ 截图/测试产物已 git add
□ python -m pytest tests/ -v 全绿
□ git tag 里程碑（可选）
```

### 方案 C：记忆系统触发规则

在 memory 中记录一条用户反馈，内容为"commit 前必须先同步 tracking 文档"，这样每次 session 启动时 context 中自动出现该提醒。

---

## 📋 应用方式

建议 **V10+V11+V12 写入 CLAUDE.md**（语义最清晰、永不丢失），`commit_checklist.md` 作为可选项。本次修复已先将方案 C 写入记忆作为 session 提醒。