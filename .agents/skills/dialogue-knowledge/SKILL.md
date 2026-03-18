---
name: dialogue-knowledge
description: '从 Cursor/Claude/CodeBuddy 等 AI 编程工具中收集对话记录，用 AI 提炼为结构化笔记，管理个人知识库。触发词：/知识库, /kb, "帮我整理对话", "对话知识库"'
---

# AI 对话知识库

## Overview

帮助用户收集散落在多个 AI 编程工具中的对话记录，用 AI 提炼为有价值的笔记，沉淀为个人知识库。

**支持的工具：** Cursor、Claude Code、claude-internal、CodeBuddy

**核心工具：** 本 SKILL 目录下的 `scripts/dialogue-kb.py` — 纯 Python 标准库 CLI，零外部依赖。

## 使用流程

用户触发此 SKILL 时，按以下流程引导：

### Step 1: 了解意图

用户可能想做以下事情之一：
- **收集**：扫描并收集 AI 对话到本地
- **提炼**：对已收集的对话用 AI 生成笔记
- **浏览**：查看/搜索已有对话或笔记
- **统计**：查看知识库概览

如果用户意图不明确，询问想做什么。

### Step 2: 执行对应操作

#### 收集对话

1. 先运行扫描看看有哪些数据：

```bash
python3 <SKILL_DIR>/scripts/dialogue-kb.py scan -v
```

2. 展示扫描结果给用户，确认后执行收集：

```bash
python3 <SKILL_DIR>/scripts/dialogue-kb.py collect
```

3. 如果用户提到远程机器，添加 `--remote` 参数：

```bash
python3 <SKILL_DIR>/scripts/dialogue-kb.py collect --remote DevCloud ecovision-prod
```

#### 提炼笔记

1. 先列出已收集的对话：

```bash
python3 <SKILL_DIR>/scripts/dialogue-kb.py list --limit 10
```

2. 用户选择要提炼的对话后，查看详情：

```bash
python3 <SKILL_DIR>/scripts/dialogue-kb.py show <编号或ID>
```

3. 阅读对话内容后，使用你自身的 AI 能力来提炼笔记。按以下规则：

**判值：** 先判断对话是否有价值。以下情况跳过：
- 只有问题没有回答
- 闲聊/问天气/问时事
- 极短对话（< 3 轮实质交互）
- 纯文件操作无实质讨论

**识别类型：**
| 类型 | 场景 | 笔记结构 |
|------|------|----------|
| debug | 排查问题 | 问题现象 → 排查过程 → 根因 → 解决方案 |
| research | 技术调研 | 背景 → 调研维度 → 方案对比 → 结论 |
| implementation | 功能实现 | 需求 → 技术方案 → 关键实现 → 注意事项 |
| optimization | 性能/重构 | 问题指标 → 优化手段 → 效果对比 |
| learning | 学习概念 | 核心概念 → 关键点 → 实践要点 |

**生成笔记：** 输出一篇 Markdown 笔记，保存到 `~/.ai-dialogues/notes/` 目录：

```
~/.ai-dialogues/notes/YYYY-MM-DD-<title-slug>.md
```

笔记文件格式：
```markdown
---
title: <标题>
type: <debug|research|implementation|optimization|learning>
tags: [tag1, tag2]
source_tool: <cursor|claude|claude-internal|codebuddy>
source_id: <对话ID>
created: <YYYY-MM-DD>
---

<笔记正文，按类型对应的结构组织>
```

4. 如果用户有 notion-note SKILL，可以建议同步到 Notion。

#### 浏览知识库

```bash
# 列出所有对话
python3 <SKILL_DIR>/scripts/dialogue-kb.py list

# 搜索
python3 <SKILL_DIR>/scripts/dialogue-kb.py list "关键词"

# 按工具筛选
python3 <SKILL_DIR>/scripts/dialogue-kb.py list --source cursor

# 统计概览
python3 <SKILL_DIR>/scripts/dialogue-kb.py stats
```

展示结果时用清晰的格式呈现给用户。

## 脚本路径（`<SKILL_DIR>` 的解析）

脚本 `dialogue-kb.py` 位于本 SKILL 目录下的 `scripts/` 子目录中。

由于 SKILL 通过符号链接分发，需要解析真实路径。使用以下方式定位 `<SKILL_DIR>`：

```bash
# 方法 1: 从 SKILL.md 所在目录解析（推荐）
SKILL_DIR="$(cd "$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")" && pwd)"

# 方法 2: 常见路径逐个尝试
for dir in \
  "./.agents/skills/dialogue-knowledge" \
  "$HOME/.agents/skills/dialogue-knowledge" \
  "./.cursor/skills/dialogue-knowledge" \
  "$HOME/.cursor/skills/dialogue-knowledge" \
  "./.claude/skills/dialogue-knowledge" \
  "$HOME/.claude/skills/dialogue-knowledge" \
  "./.codebuddy/skills/dialogue-knowledge" \
  "$HOME/.codebuddy/skills/dialogue-knowledge"; do
  [ -f "$dir/scripts/dialogue-kb.py" ] && SKILL_DIR="$dir" && break
done
```

AI Agent 应该用 Glob 或 Shell 工具先找到脚本，然后用绝对路径调用。

## Key Principles

- **轻量优先** — 脚本零依赖，SKILL 驱动 AI 自身能力做提炼
- **渐进式** — 先收集、再提炼、按需同步，不要求一次做完
- **一次一个问题** — 不要一次性处理太多对话，每次提炼 1-3 条为宜
- **尊重用户选择** — 哪些对话值得提炼由用户决定，AI 只做建议
