# Cross-Agent Setup Guide

This guide explains how to configure different AI agents to use the note-keeper skill
with their Notion MCP connection.

## Prerequisites (All Agents)

1. A Notion integration token with access to your workspace
2. The Notion MCP server installed and configured
3. The Knowledge Base database created in your Notion workspace

## Claude Code

**Step 1: Configure Notion MCP**

Add to your Claude Code MCP settings (global or project-level):

```json
{
  "mcpServers": {
    "notion": {
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "env": {
        "OPENAPI_MCP_HEADERS": "{\"Authorization\": \"Bearer YOUR_NOTION_TOKEN\", \"Notion-Version\": \"2022-06-28\"}"
      }
    }
  }
}
```

**Step 2: Load the skill**

Option A — Register as a Skill (recommended):
Place the `note-keeper/` directory in your project or global skills location.

Option B — Include in CLAUDE.md:
Copy the content of SKILL.md into your project's `CLAUDE.md` or `AGENTS.md`.

## Cursor

**Step 1: Configure Notion MCP**

Add to `.cursor/mcp.json` in your project root:

```json
{
  "mcpServers": {
    "notion": {
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "env": {
        "OPENAPI_MCP_HEADERS": "{\"Authorization\": \"Bearer YOUR_NOTION_TOKEN\", \"Notion-Version\": \"2022-06-28\"}"
      }
    }
  }
}
```

**Step 2: Load the skill**

Copy SKILL.md to `.cursor/rules/note-keeper.md` (remove the YAML frontmatter — Cursor
rules use plain markdown).

## CodeBuddy

**Step 1: Configure Notion MCP**

Follow CodeBuddy's MCP configuration documentation to add the Notion MCP server.

**Step 2: Load the skill**

Add the SKILL.md content to your project rules or inject it via system prompt configuration.

## Other Agents (Generic)

For any AI agent that supports:
- **MCP protocol**: Configure the Notion MCP server per the agent's MCP documentation
- **Custom instructions / system prompts**: Inject the SKILL.md content as part of the
  system prompt or project-level instructions

The key requirements are:
1. The agent can call Notion MCP tools (`notion-search`, `notion-fetch`, `notion-create-pages`, etc.)
2. The agent has the note-keeper instructions in its context

## Verifying Setup

After configuring, test with a simple command:

```
搜一下知识库里有什么
```

If the agent can search the Knowledge Base database and return results (or confirm it's empty),
the setup is working correctly.
