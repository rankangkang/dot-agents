---
name: note
description: 快速记录知识笔记到 Notion Knowledge Base
triggers:
  - /note
  - 记一下
  - note this
---

# /note — 记录知识笔记

使用 `notion-note` Skill 将知识点保存到 Notion Knowledge Base。

## 使用方式

```
/note <要记录的内容或上下文描述>
```

**示例：**
- `/note TypeScript 中 satisfies 关键字的用法和场景`
- `/note` （无参数时，从当前对话上下文中提取值得记录的知识点）
- `记一下刚才解决的这个 bug`

## 执行流程

当用户触发此命令时，按以下步骤执行：

1. **读取 Skill** — 读取 `.agents/skills/notion-note/SKILL.md` 并严格遵循其中的指令
2. **提取知识** — 从用户提供的内容或当前对话上下文中，识别核心知识点
3. **草拟元数据** — 生成 Title、Category、Tags、Source、Importance、Agent
4. **确认** — 向用户展示笔记摘要，等待确认
5. **写入 Notion** — 确认后通过 Notion MCP 写入 Knowledge Base 数据库

## 注意事项

- 执行前必须先完整读取 notion-note SKILL，其中包含数据库 schema、写作规范、去重逻辑等关键细节
- 一条笔记对应一个知识点，如需记录多个知识点请分别创建
- 匹配用户语言：用户用中文就写中文笔记，用英文就写英文笔记
