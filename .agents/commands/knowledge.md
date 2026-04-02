---
name: knowledge
triggers:
  - /知识库
  - /kb
  - /knowledge
description: 管理 AI 对话知识库 — 收集、提炼、浏览
---

使用 `dialogue-knowledge` SKILL 来管理 AI 对话知识库。

根据用户的意图执行对应操作：
- 先读取 `dialogue-knowledge/memory.md`，遵循用户已有偏好
- 如果用户想收集对话，运行扫描和收集脚本
- 如果用户想提炼笔记，列出对话并引导用户选择
- 如果用户想浏览，展示对话列表或搜索结果
- 如果用户想看统计，展示知识库概览

如果用户只说“帮我整理对话”而没给细节，走默认工作流：`collect -> triage -> show -> 提炼 -> done`。

如果需要确认 CLI 参数、远程行为、筛选规则或 `--channels` 语义，读取 `dialogue-knowledge/references/cli-commands.md`，不要在这里重复维护命令细节。
