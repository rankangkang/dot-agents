# AI 对话知识库 — 设计文档

> 把散落在 Cursor/Claude Code/CodeBuddy 等工具中的 AI 对话，同步到本地，用 AI 提炼为结构化笔记，沉淀为个人知识库。

## 架构概览

```
收集层（Shell 脚本）           提炼层（Python 脚本）         交互层（SKILL）
┌─────────────────┐      ┌──────────────────────┐      ┌──────────────┐
│ 本地扫描         │      │ 预处理（剔除噪声）    │      │ /知识库 命令  │
│ ~/.cursor/       │      │ AI 判值              │      │ collect      │
│ ~/.claude/       │─────→│ 类型识别             │─────→│ distill      │
│ ~/.claude-internal│      │ 生成结构化笔记        │      │ browse       │
│ ~/.codebuddy/    │      │ 写入 index + markdown │      │ sync→Notion  │
│                  │      └──────────────────────┘      └──────────────┘
│ SSH 远程 rsync   │              ↓
└─────────────────┘      ~/.ai-dialogues/
                         ├── archive/     原始对话
                         ├── notes/       提炼笔记
                         ├── index.json   元数据索引
                         └── config.yaml  配置
```

## 数据源

| 工具 | 目录 | 对话路径模式 | 格式 |
|------|------|-------------|------|
| Cursor | `~/.cursor/` | `projects/*/agent-transcripts/*/*.jsonl` | JSONL (role + message.content[]) |
| Claude Code | `~/.claude/` | `projects/**/*.jsonl` | JSONL (type + message + timestamp) |
| claude-internal | `~/.claude-internal/` | `projects/**/*.jsonl` | JSONL (同 Claude Code) |
| CodeBuddy | `~/.codebuddy/` | 待探查具体结构 | 待确认 |

远程机器通过 `~/.ssh/config` 中的 Host 连接，用 rsync 增量同步到本地归档。

## 提炼策略

### 判值规则

无价值直接跳过：
- 只有问题没有回答
- 闲聊/问天气/问时事
- 极短对话（< 3 轮）
- 纯文件操作无实质讨论

### 笔记类型

| 类型 | 场景 | 笔记结构 |
|------|------|----------|
| debug | 排查问题 | 问题现象 → 排查过程 → 根因 → 解决方案 |
| research | 技术调研 | 背景 → 调研维度 → 方案对比 → 结论 |
| implementation | 功能实现 | 需求 → 技术方案 → 关键实现 → 注意事项 |
| optimization | 性能/重构 | 问题指标 → 优化手段 → 效果对比 |
| learning | 学习概念 | 核心概念 → 关键点 → 实践要点 |
| other | 其他 | 摘要 + 要点列表 |

### 预处理

送入 AI 前剔除噪声：
- `<thinking>` 块、`<antml_function_calls>` 块
- `tool_use` / `tool_result` 消息
- `file-history-snapshot` 类型
- 超长代码块截断（保留首尾 20 行）

### 输出格式

```json
{
  "value": "high|medium|low|none",
  "value_reason": "...",
  "type": "debug|research|implementation|optimization|learning|other",
  "title": "标题",
  "tags": ["python", "fastapi"],
  "summary": "一句话摘要",
  "note": "## 问题现象\n\n..."
}
```

## 文件结构

```
.agents/
├── skills/dialogue-knowledge/
│   ├── SKILL.md                  # 交互流程定义
│   ├── scripts/
│   │   └── dialogue-kb.py       # CLI 工具（扫描/收集/解析/索引/浏览）
│   └── references/
│       └── data-sources.md       # 数据源注册表
└── commands/
    └── knowledge.md              # /知识库 命令
```

## 存储设计

本地 Markdown 为真相源，Notion 为可选同步目标。

```
~/.ai-dialogues/
├── config.yaml           # 用户配置
├── index.json            # 全局索引
├── archive/              # 原始对话归档
│   ├── cursor/
│   │   └── <project>/
│   │       └── <uuid>.jsonl
│   ├── claude/
│   │   └── <host>/<project>/
│   │       └── <uuid>.jsonl
│   └── ...
└── notes/                # 提炼笔记
    ├── 2026-03-15-fastapi-json-parse-bug.md
    └── 2026-03-16-tauri-vs-electron.md
```
