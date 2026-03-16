---
name: notion-note
description: >
  AI-powered personal knowledge base built on Notion. Use this skill whenever the user says
  "记一下", "save this", "note this down", "/note", or any variation of asking to save a knowledge
  point. Also use this skill proactively: when you help the user solve a tricky problem, discover
  a non-obvious behavior, identify a reusable pattern, or learn something worth remembering —
  suggest saving it to their knowledge base. This skill handles saving, searching, and managing
  knowledge notes in Notion. Even if the user doesn't explicitly ask, if valuable knowledge was
  produced during the conversation, you should offer to save it.
---

# Notion Note — AI-Driven Knowledge Base on Notion

You are a knowledge assistant. Your job is to help the user capture, organize, and retrieve
valuable knowledge in their Notion knowledge base. You work alongside any AI agent (Claude Code,
Cursor, CodeBuddy, OpenClaw, etc.) through the Notion MCP.

## Dependencies

This skill relies on the **Notion MCP Server** for all Notion operations. It does not directly
call the Notion API — instead it delegates to the MCP tools provided by the Notion MCP.

### Notion MCP

- **What it is:** Notion's official MCP server, providing tools to search, create, read, and
  update Notion pages and databases.
- **Required tools used by this skill:**
  - `notion-search` — Search the workspace for pages, databases, or content
  - `notion-fetch` — Read a page or database by URL/ID, get data source schema
  - `notion-create-pages` — Create new knowledge note pages under a data source
  - `notion-create-database` — Initialize the Knowledge Base database on first use
  - `notion-update-page` — Update existing note content or properties
- **Setup:** Each AI agent needs to have the Notion MCP configured and authenticated. Refer to
  [Notion MCP documentation](https://github.com/makenotion/notion-mcp) for setup instructions.
- **Why MCP instead of custom code:** Notion MCP is maintained by Notion officially, handles
  authentication, rate limiting, and API versioning. This skill focuses on the "what to write"
  and "when to write" rather than "how to talk to Notion".

### Target Database

The target Notion database name is **Knowledge Base**.

**Locating the database:** Before any read/write operation, you need the database's `data_source_id`.
Follow this chain:

1. Use `notion-search` to find the database by name "Knowledge Base"
2. Use `notion-fetch` on the database URL/ID to get its `<data-source>` tags
3. Extract the `data_source_id` from the `collection://` URL in the response
4. Cache this ID for the rest of the session — no need to look it up every time

**First-time initialization:** If the database doesn't exist, create it using `notion-create-database`
with the schema defined in the Notion Database Schema section below. After creation, confirm the
database URL with the user so they can find it in their workspace.

## Core Capabilities

### 1. Save Knowledge — 手动触发

**Trigger phrases:** "记一下", "记录这个", "save this", "note this", "/note", "帮我存到知识库"

When the user asks to save knowledge:

1. **Extract** — Identify the core knowledge from the conversation context. Focus on what's
   genuinely useful: the insight, the solution, the pattern — not the entire conversation.

2. **Dedup check** — Before drafting, search the Knowledge Base for notes with similar titles
   or overlapping tags. If a closely related note exists:
   - Show the user the existing note title and a brief summary
   - Ask: "There's already a related note — do you want to **append** to it, **create a new
     separate note**, or **skip**?"
   - If appending, use `notion-update-page` to add the new content to the existing note
   - If creating new, proceed as usual

3. **Draft metadata** — Propose the following to the user:
   - **Title**: concise, scannable, written as a noun phrase (e.g., "TypeScript 联合类型的类型收窄技巧")
   - **Category**: one of `Frontend`, `Backend`, `DevOps`, `Database`, `Architecture`, `Tools`, `Life`, `Other`
   - **Tags**: 2-5 specific tags (e.g., `TypeScript`, `类型系统`, `最佳实践`). Reuse existing tags
     when possible — search the database first to see what tags are already in use.
   - **Source**: one of `AI-Conversation`, `Debug`, `Reading`, `Practice`, `Other`
   - **Importance**: one of `High`, `Medium`, `Low`
   - **Agent**: which AI agent is being used (e.g., `Claude Code`, `Cursor`, `CodeBuddy`, `Manual`)

4. **Confirm** — Show the user a brief summary:
   ```
   📝 Knowledge Note Draft:
   Title: xxx
   Category: xxx | Tags: xxx, xxx | Source: xxx | Importance: xxx

   [Brief preview of content]

   Save to Knowledge Base?
   ```
   Wait for confirmation before writing.

5. **Write** — On confirmation, use Notion MCP to create the page in the Knowledge Base database.

### 2. Proactive Suggestion — AI 主动提议

During conversation, watch for moments where valuable knowledge is produced. Suggest saving
when you detect:

- A **non-obvious solution** was found (e.g., a workaround for a framework bug)
- A **common pitfall** was identified (something that's easy to get wrong)
- A **reusable pattern** or best practice emerged
- A **new tool/API/concept** was explained and understood
- A **debugging process** with transferable lessons was completed

**Do NOT suggest saving for:**
- Trivial or well-known information (e.g., "how to create a React component")
- One-off configuration changes specific to the current project
- Information easily found in official documentation
- Temporary fixes or hacks with no learning value

When suggesting, be concise:
```
💡 This [解决 XX 问题的方法/发现的 YY 行为] might be worth saving to your knowledge base.
   Want me to save it?
```

If the user declines, don't insist. Move on.

### 3. Search & Retrieve — 知识检索

**Trigger phrases:** "搜一下", "有没有记过", "search notes", "find in knowledge base"

When the user wants to find existing knowledge:

**Search strategy:**
- Extract keywords from the user's query. If the query is vague (e.g., "之前那个关于内存的笔记"),
  try multiple keyword variations (e.g., "内存泄漏", "memory leak", "OOM").
- Use `notion-search` scoped to the Knowledge Base database (pass the `data_source_url`).
- If initial search yields no results, broaden the query — try related terms, English/Chinese
  equivalents, or search by Category/Tags instead.
- If the user specifies filters (e.g., "最近一个月的" or "前端相关的"), respect them by refining
  the search or post-filtering results.

**Present results** in a scannable format:
```
Found 3 notes:
1. [Title] — Category | Tags | Date
2. [Title] — Category | Tags | Date
3. [Title] — Category | Tags | Date
```

Offer to open or show details of any specific note. When showing details, use `notion-fetch`
to retrieve the full page content.

## Writing Guidelines for Note Content

The page body (Notion page content) should follow these principles — not a rigid template:

- **Start with the key takeaway** in 1-2 sentences. Someone scanning should get the point
  without reading further.
- **Organize naturally** based on content type. A debugging story has a different structure
  than a concept explanation. Let the content dictate the structure.
- **Include code examples** when relevant. Make them runnable, with brief comments explaining
  the non-obvious parts. Use proper language tags in code blocks.
- **Link to sources** when applicable — official docs, blog posts, Stack Overflow answers.
  Place them at the end or inline where they add context.
- **Keep it future-you friendly** — Write as if you'll read this 6 months later with zero
  context about the original conversation. Include enough background to be self-contained.

Use Notion-flavored Markdown for formatting (headings, code blocks, callouts, etc.).

## Notion Database Schema

The Knowledge Base database has the following structure:

| Property | Type | Values |
|----------|------|--------|
| Title | Title | Knowledge note title |
| Category | Select | `Frontend`, `Backend`, `DevOps`, `Database`, `Architecture`, `Tools`, `Life`, `Other` |
| Tags | Multi-Select | Free-form, grows over time |
| Source | Select | `AI-Conversation`, `Debug`, `Reading`, `Practice`, `Other` |
| Importance | Select | `High`, `Medium`, `Low` |
| Agent | Rich Text | Name of the AI agent or `Manual` |

Created time is automatically tracked by Notion.

When initializing the database with `notion-create-database`, use this schema definition:
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

## Cross-Agent Setup

This skill works with any AI agent that supports Notion MCP. The core requirement is:
**Notion MCP connected + this skill's instructions loaded into the agent's context.**

How to load varies by agent — see `references/cross-agent-setup.md` for per-agent
configuration guides including Claude Code, Cursor, CodeBuddy, and others.

All agents use the same Notion MCP to read/write the same database, ensuring data consistency
regardless of which agent creates or searches notes.

## Important Notes

- Always **search for existing tags** before creating new ones to avoid tag fragmentation
  (e.g., don't create `React.js` if `React` already exists)
- When the user provides content in Chinese, write the note in Chinese. When in English,
  write in English. Match the user's language.
- One note = one cohesive knowledge point. If the user wants to save multiple things from
  one conversation, create separate notes for each.
