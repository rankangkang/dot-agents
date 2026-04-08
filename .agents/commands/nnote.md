---
name: nnote
description: 将知识点记入 Notion Knowledge Base（委托 notion-note）
triggers:
  - /nnote
  - 记一下
  - note this
---

使用 `notion-note` SKILL：先完整读取 `.agents/skills/notion-note/SKILL.md`（含数据库 schema、去重、写作规范），再按其中步骤执行；不要在本文件重复流程细节。

**用法示例：** `/nnote TypeScript satisfies 的用法`；无参数时从当前对话提取可记录点。语言与笔记正文与用户一致（中文对话写中文）。
