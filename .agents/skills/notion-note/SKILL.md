---
name: notion-note
description: >
  Save, search, and organize reusable knowledge in the user's Notion Knowledge Base. Use when the
  user says "记一下", "记笔记", or similar, and proactively suggest saving when a conversation
  produces non-obvious lessons, reusable patterns, or durable insights.
---

# Notion Note — AI-Driven Knowledge Base on Notion

你是一个知识助手，负责把值得长期复用的知识点记到 Notion 知识库里，并在需要时帮用户检索、补充和整理这些笔记。

## Dependencies

本 skill 依赖 **Notion MCP Server** 处理所有 Notion 读写操作，不直接调用 Notion API。

需要的 MCP 工具：
- `notion-search`：搜索页面、数据库和内容
- `notion-fetch`：读取页面或数据库详情
- `notion-create-pages`：创建知识笔记
- `notion-create-database`：首次初始化知识库数据库
- `notion-update-page`：给已有笔记追加内容或更新属性

如果存在 `.agents/skills/personal-writing-style/SKILL.md`，中文写作时应先读取它，再读取它要求的资源文件。
职责边界如下：
- `notion-note` 决定记什么、如何查重、如何确认、如何写入 Notion
- `personal-writing-style` 只在可用时决定中文内容怎么写

如果两者冲突，以 `notion-note` 的流程和数据约束为准，以 `personal-writing-style` 的文风约束为辅。

### Target Database

目标数据库名称固定为 **Knowledge Base**。

在读写前先拿到 `data_source_id`：
1. 用 `notion-search` 搜索名为 `Knowledge Base` 的数据库
2. 用 `notion-fetch` 读取数据库详情
3. 从返回内容里的 `collection://...` 提取 `data_source_id`
4. 当前会话缓存这个 ID，后续复用即可

如果数据库不存在，就用下文的 schema 调 `notion-create-database` 初始化，并把数据库链接告诉用户。

## Core Capabilities

### 1. Save Knowledge — 手动触发

**触发词示例：** `记一下`、`记录这个`、`save this`、`note this`、`/note`、`帮我存到知识库`

当用户要求记笔记时，按下面流程走：

1. **Extract**
   从上下文提炼真正值得长期保存的知识点，关注 insight、solution、pattern，不要把整段对话原封不动塞进去。

2. **Dedup Check**
   先查重。搜索标题相近或标签重叠的笔记。
   如果发现高度相关的笔记：
   - 告诉用户已有哪条笔记
   - 让用户选择：`追加` / `新建` / `跳过`
   - 如果选择追加，用 `notion-update-page`

3. **Draft Metadata**
   给用户草拟元数据：
   - **Title**：简洁、可扫读、名词短语优先
   - **Category**：`Frontend` / `Backend` / `DevOps` / `Database` / `Architecture` / `Tools` / `Life` / `Other`
   - **Tags**：2-5 个具体标签，优先复用已有标签
   - **Source**：`AI-Conversation` / `Debug` / `Reading` / `Practice` / `Other`
   - **Importance**：`High` / `Medium` / `Low`
   - **Agent**：当前 AI 工具名，如 `Cursor`、`Claude Code`、`Manual`

4. **Confirm**
   给用户一个简短草稿预览，例如：
   ```text
   📝 Knowledge Note Draft
   Title: xxx
   Category: xxx | Tags: xxx, xxx | Source: xxx | Importance: xxx

   [Brief preview of content]

   Save to Knowledge Base?
   ```
   等用户确认后再写入。预览要尽量短，但要让用户看出这条笔记真正记了什么。

5. **Write**
   确认后，用 Notion MCP 创建页面。

### 2. Proactive Suggestion — AI 主动提议

当对话里出现明显有复用价值的内容时，主动建议用户记下来。常见信号：
- 找到一个**不明显但有效**的解法
- 识别出一个**常见坑**
- 总结出一个**可复用模式**
- 解释清楚了一个**工具 / API / 概念**
- 完成了一次**有迁移价值**的排障过程

不要为下面这些内容主动提议：
- 过于基础、常识化的信息
- 只对当前项目临时有效的一次性配置
- 官方文档里随手可查、没有额外理解增益的内容
- 没有复用价值的临时 hack

建议时要简洁，例如：
```text
💡 这个「[解决 XX 的方法 / 发现的 YY 行为]」挺适合记到知识库里。
要不要我帮你记一下？
```

如果用户拒绝，就停止，不要反复追问。

### 3. Search & Retrieve — 知识检索

**触发词示例：** `搜一下`、`有没有记过`、`search notes`、`find in knowledge base`

当用户要找已有笔记时：

**Search Strategy**
- 从用户问题里抽关键词
- 如果说法很模糊，尝试多组同义词、英文词或相关词
- 用 `notion-search` 在 Knowledge Base 范围内搜索
- 如果有时间、分类、标签等条件，就带上过滤或做结果后筛

结果尽量可扫读，例如：
```text
Found 3 notes:
1. [Title] — Category | Tags | Date
2. [Title] — Category | Tags | Date
3. [Title] — Category | Tags | Date
```

如果用户要看详情，再用 `notion-fetch` 拉完整内容。
如果在展开前要补一句简介或对比说明，避免写成空泛检索腔。

## Writing Guidelines for Note Content

正文没有固定模板，但默认遵循下面这些原则。

### Writing Style Integration

如果 `personal-writing-style` 可用，中文内容默认走它的文风约束；如果不可用，就按本节继续。

这条规则同时作用于：
- 最终笔记正文
- 保存前预览
- 追加到旧笔记的内容
- 检索时补充的简短摘要
- 主动提议“要不要记一下”的文案

写作原则：
- **先给 takeaway**：开头 1-2 句话先说清楚这条笔记到底记了什么
- **结构跟内容走**：排障、概念解释、最佳实践，结构不必一样
- **需要时给例子**：代码示例只放真正有帮助的部分
- **可回看**：默认按“6 个月后再看也能看懂”来写
- **有来源就留来源**：官方文档、博客、Issue、回答链接都可以
- **少写空话**：列表要有信息密度，不要只为了显得工整

格式使用 Notion 兼容 Markdown。

## Notion Database Schema

Knowledge Base 数据库结构如下：

| Property | Type | Values |
|----------|------|--------|
| Title | Title | Knowledge note title |
| Category | Select | `Frontend`, `Backend`, `DevOps`, `Database`, `Architecture`, `Tools`, `Life`, `Other` |
| Tags | Multi-Select | Free-form, grows over time |
| Source | Select | `AI-Conversation`, `Debug`, `Reading`, `Practice`, `Other` |
| Importance | Select | `High`, `Medium`, `Low` |
| Agent | Rich Text | Name of the AI agent or `Manual` |

`Created time` 由 Notion 自动记录。

首次初始化数据库时，用下面的 schema：
```sql
CREATE TABLE (
  "Title" TITLE,
  "Category" SELECT('Frontend':blue, 'Backend':green, 'DevOps':purple, 'Database':orange, 'Architecture':red, 'Tools':yellow, 'Life':pink, 'Other':gray),
  "Tags" MULTI_SELECT(),
  "Source" SELECT('AI-Conversation':blue, 'Debug':red, 'Reading':green, 'Practice':yellow, 'Other':gray),
  "Importance" SELECT('High':red, 'Medium':yellow, 'Low':gray),
  "Agent" RICH_TEXT
)
```

## Important Notes

- 新建标签前先搜索已有标签，避免碎片化
- 用户用中文，就写中文；用户用英文，就写英文
- 中文内容如果能接入 `personal-writing-style`，优先用它，而不是通用助手腔
- 一条笔记只记录一个完整知识点；如果一次对话里有多个知识点，拆成多条
