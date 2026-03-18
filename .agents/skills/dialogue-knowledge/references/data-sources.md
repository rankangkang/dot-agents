# 数据源注册表

AI 编程工具的对话数据存储位置与格式。

## 已支持

| 工具 | 家目录 | 对话路径 | 格式 | 解析器 |
|------|--------|----------|------|--------|
| Cursor | `~/.cursor/` | `projects/*/agent-transcripts/*/*.jsonl` | JSONL (role + message.content[]) | `parse_cursor_jsonl` |
| Claude Code | `~/.claude/` | `projects/**/*.jsonl` | JSONL (type + message + timestamp) | `parse_claude_jsonl` |
| claude-internal | `~/.claude-internal/` | `projects/**/*.jsonl` | JSONL (同 Claude Code) | `parse_claude_jsonl` |
| CodeBuddy | `~/.codebuddy/` | `projects/**/*.jsonl` | JSONL (待确认) | `parse_claude_jsonl` |

## JSONL 格式差异

### Cursor agent-transcripts

```json
{"role": "user", "message": {"content": [{"type": "text", "text": "..."}]}}
{"role": "assistant", "message": {"content": [{"type": "text", "text": "..."}]}}
```

特点：
- `role` 字段区分角色
- `message.content` 是数组，每项有 `type` + `text`
- 用户消息可能被 `<user_query>` 标签包裹
- 包含 `<rules>`, `<memories>`, `<agent_skills>` 等系统信息需过滤

### Claude Code / claude-internal

```json
{"type": "user", "message": {"content": "..."}, "timestamp": "...", "sessionId": "...", "cwd": "..."}
{"type": "assistant", "message": {"content": [{"type": "text", "text": "..."}, {"type": "tool_use", ...}]}}
```

特点：
- `type` 字段区分角色（不是 `role`）
- `message.content` 可能是字符串或数组
- 包含 `timestamp`, `cwd`, `sessionId` 等元数据
- 有 `isSidechain` 字段标记分支对话（应跳过）
- 有 `file-history-snapshot` 类型的非对话条目（应跳过）

## 噪声过滤

以下内容在解析时自动剔除：
- `<thinking>` 块（AI 思考过程）
- `<antml_function_calls>` / `<function_calls>` 块（工具调用）
- `<tool_use>` / `<tool_call>` / `<tool_result>` 块
- `<rules>` / `<memories>` / `<user_info>` 等系统注入
- `<attached_files>` / `<open_and_recently_viewed_files>` 等上下文注入
- `<agent_skills>` 块

## 待支持

| 工具 | 说明 | 状态 |
|------|------|------|
| Cursor chatSessions | `~/Library/App Support/Cursor/.../chatSessions/*.json` — JSON 格式旧版聊天 | 待实现 |
| Cursor SpecStory | `<project>/.specstory/history/*.md` — Markdown 格式 | 待实现 |
| codex-internal | 腾讯内部 Codex fork，路径待确认 | 待探查 |
