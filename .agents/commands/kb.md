---
name: kb
description: 管理 AI 对话知识库 — 收集、提炼、浏览（委托 dialogue-knowledge）
triggers:
  - /kb
  - /knowledge
---

使用 `dialogue-knowledge` SKILL：先读取 `.agents/skills/dialogue-knowledge/SKILL.md`，再按其中人机协作边界与默认工作流执行。

**首步偏好：** 若存在 `dialogue-knowledge/memory.md`，先读并遵循。

**意图路由（细则以 SKILL 为准）：**
- 收集 / 扫描 → 按 SKILL 调用 `dialogue-kb.py`（CLI 参数见 `dialogue-knowledge/references/cli-commands.md`）
- 提炼 → triage 后让用户选对话，再生成草稿并门控确认
- 浏览 / 搜索 → 列表或检索结果展示给用户
- 统计 → 知识库概览

用户仅说「帮我整理对话」且无细节时，默认链路：`collect → triage → show → 提炼 → done`（见 SKILL「默认工作流」）。
