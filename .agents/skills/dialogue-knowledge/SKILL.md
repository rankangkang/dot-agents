---
name: dialogue-knowledge
description: '从 Cursor/Claude/CodeBuddy 等 AI 编程工具中收集对话记录，用 AI 提炼为结构化笔记，管理个人知识库。触发词：/知识库, /kb, "帮我整理对话", "对话知识库"'
---

# AI 对话知识库

从 Cursor、Claude Code、claude-internal、CodeBuddy（插件 + IDE）中收集对话记录，用 AI 提炼为结构化笔记，沉淀为个人知识库。

## 找到脚本

本 SKILL 的 CLI 工具在同目录 `scripts/dialogue-kb.py`。由于 SKILL 可能通过符号链接分发，先用 Glob 找到脚本的真实路径：

```
**/skills/dialogue-knowledge/scripts/dialogue-kb.py
```

找到后用绝对路径调用，后续示例中用 `$KB` 代替完整路径。

## 快速开始

如果用户第一次使用，或者说了"帮我整理对话"但没指定具体操作，按以下流程一条龙走完：

1. `$KB collect` — 收集本地对话到归档
2. `$KB triage` — 获取待提炼对话摘要
3. 从 triage 结果中挑出 3-5 条最有价值的（标题有明确技术内容的），展示给用户
4. 用户选择后，逐条 `$KB show` + 提炼 + `$KB done`

不需要一次处理完所有对话——每次 1-3 条即可，下次再来继续。

## 流程

### 1. 判断意图

用户可能想做以下事情之一（如不明确则询问）：

| 意图 | 关键词 | 操作 |
|------|--------|------|
| 收集 | "收集对话"、"同步"、"扫描" | → 执行收集 |
| 提炼 | "提炼"、"总结"、"生成笔记" | → 执行提炼 |
| 浏览 | "看看"、"搜索"、"列出" | → 执行浏览 |
| 统计 | "有多少"、"概览" | → `$KB stats` |

### 2. 收集对话

```bash
# 扫描看有哪些数据
$KB scan -v

# 收集到本地归档（增量，只同步变更文件）
$KB collect

# 含远程机器（加 -v 看详细日志）
$KB collect --remote DevCloud -v
```

收集完成后展示统计摘要（新增 X 条、更新 Y 条、未变 Z 条）。

### 3. 提炼笔记

这是核心价值步骤。遵循以下流程：

#### 3.1 筛选对话（三层漏斗）

```
Layer 0: 脚本自动过滤     → < 2 turns / 无回复 / 纯命令 → 自动 skipped
Layer 1: AI 批量判值       → 读摘要信息，批量决定值不值得看
Layer 2: AI 深度阅读       → 只对值得的对话做全文阅读
```

**Layer 0** 在索引阶段自动完成，无需 Agent 参与。

**Layer 1** 是关键——用 `triage` 命令获取所有待提炼对话的摘要：

```bash
$KB triage
```

输出 JSON 格式，每条包含 `id`、`title`、`first_question`、`turns`、`tool`、`host`。**不含对话全文**，数据量很小。

拿到 triage 数据后，Agent 应该：
1. 扫描所有条目的 `title` 和 `first_question`
2. 判断每条是否值得深入阅读，分为三类：
   - **值得提炼** — 有明确问题、排查过程、技术讨论
   - **可能有价值** — 不确定，需要看全文才能判断
   - **跳过** — 闲聊、纯命令、极短无内容
3. 将"跳过"的**批量执行** `$KB skip <ID1> <ID2> <ID3> --reason "无实质内容"`
4. 将"值得提炼"和"可能有价值"的列表展示给用户，让用户挑选

**Layer 2** 用户选择后，用 `$KB show <编号>` 深度阅读，然后决定提炼或跳过。

#### 3.2 阅读对话

```bash
$KB show <编号>          # 自动截断超长内容
$KB show <编号> --full   # 查看完整对话，不截断
```

**注意：** 对话可能很长（100+ turns）。`show` 默认会截断每轮超长内容（前 1000 + 后 500 字符），使用 `--full` 查看完整内容。阅读时重点关注：
- 用户的原始问题是什么
- 最终是否解决了问题
- 过程中有哪些关键转折点
- 是否产生了可复用的知识

#### 3.3 判断价值

**直接跳过的情况（标记为 skipped）：**
- 只有问题没有回答
- 闲聊、问天气、问时事
- 极短对话（< 3 轮实质交互）
- 纯文件操作/代码生成无实质讨论
- 对话中断、未完成

**值得提炼的信号：**
- 多轮排查后解决了一个问题
- 对比了多种技术方案
- 实现了一个完整功能并踩了坑
- 学到了新概念或最佳实践

#### 3.4 生成笔记

##### 写作原则

- 写给一个月后的自己——开头 1-2 句话就让人知道这篇在讲什么
- 让内容决定结构，不要硬套模板——需要标题就加，不需要就别加
- 重点写反直觉的、容易忘的、容易踩坑的，不写常识
- 代码只保留不查文档就想不起来的关键片段
- 不要复述对话过程，不要面面俱到——只留最有价值的部分
- 一条对话生成一篇笔记

参考 `references/example-notes/` 了解风格。

##### 笔记元数据

frontmatter 字段与 `notion-note` Knowledge Base 对齐，方便通过 notion 通道推送：

```yaml
title: <具体标题>
type: debug | research | implementation | optimization | learning
category: Frontend | Backend | DevOps | Database | Architecture | Tools | Life | Other
tags: [具体技术标签, 2-5 个]
source_tool: cursor | claude | codebuddy | codebuddy-ide
source_id: <对话ID>
created: YYYY-MM-DD
```

推送到 Notion 时的字段映射：`category` → Category，`tags` → Tags，`source_tool` → Agent，`type` → Source（debug→Debug，其余→AI-Conversation）。

#### 3.5 存储笔记（通道化）

笔记的存储采用**通道（channel）**机制——类似日志库的多 sink 设计。用户可以配置多个存储通道，每个通道独立工作。

**内置通道：**

| 通道 | 存储方式 | 何时使用 |
|------|----------|----------|
| `local` | 写入 `~/.ai-dialogues/notes/YYYY-MM-DD-<slug>.md` | 默认通道，用 Write 工具写文件 |
| `notion` | 通过 `notion-note` SKILL 推送到 Notion | 用户有 Notion MCP 时 |

**执行顺序：** 询问用户想存到哪些通道（可多选），然后逐个执行。

**local 通道：** 用 Write 工具写入 Markdown 文件，包含 frontmatter：

```markdown
---
title: <具体的标题>
type: debug
category: Frontend
tags: [TypeScript, ESM, 工程化]
source_tool: cursor
source_id: <对话ID>
created: 2026-03-17
---

<笔记正文>
```

**notion 通道：** 调用 `notion-note` SKILL 将笔记内容推送到 Notion 知识库。

**其他通道：** 未来可扩展（Obsidian、语雀、飞书文档等），遵循同样的模式。

#### 3.6 更新索引状态

存储完成后，**必须运行命令更新状态**（不要手动编辑 index.json）：

```bash
# 标记为已提炼（支持批量），记录存储通道
$KB done <ID1> <ID2> --channels "notion,local" --note-title "笔记标题"

# 批量标记为跳过
$KB skip <ID1> <ID2> <ID3> --reason "纯文件操作无实质讨论"

# 误操作？重置回 pending
$KB reset <ID>
```

#### 3.7 处理 outdated 对话

如果一条已提炼的对话后续又增长了（列表中标记为 `↑N`）：

1. 用 `$KB show` 查看完整对话，重点看新增部分
2. 判断新增内容是否改变了原有结论
3. 如果是：更新对应通道中的笔记内容，然后 `$KB done <ID> --channels "..."`
4. 如果否：直接 `$KB done <ID>` 将状态改回 done

### 4. 浏览知识库

```bash
$KB list                        # 所有对话（默认 20 条）
$KB list "关键词"               # 搜索
$KB list --source cursor        # 按工具（cursor/claude/claude-internal/codebuddy/codebuddy-ide）
$KB list --host DevCloud        # 按主机
$KB list --pending              # 只看待提炼的
$KB list --days 7               # 最近一周
$KB list --since 2026-03-10     # 某日之后
$KB list --offset 20            # 翻页（跳过前 20 条）
$KB stats                       # 统计概览
```

列表中每条对话末尾的状态标记：
- `·` = pending（待提炼）
- `✔` = done（已提炼）
- `↑N` = outdated（已提炼但新增了 N 轮对话）
- 无标记 = skipped

## 命令速查

| 命令 | 说明 |
|------|------|
| `$KB scan [-v] [--remote HOST]` | 扫描本地/远程对话文件 |
| `$KB collect [-v] [--remote HOST]` | 收集对话到归档 |
| `$KB index` | 重建索引 |
| `$KB list [QUERY] [--source X] [--state X] [--pending] [--days N] [--since DATE] [--offset N] [--limit N]` | 列出/搜索对话 |
| `$KB show <ID> [--full]` | 查看对话详情 |
| `$KB triage` | 输出待提炼摘要(JSON) |
| `$KB done <ID...> [--channels X] [--note-title X]` | 标记为已提炼 |
| `$KB skip <ID...> [--reason X]` | 标记为跳过 |
| `$KB reset <ID...>` | 重置状态为 pending |
| `$KB stats` | 统计概览 |

## 关键原则

- **增量优先** — 收集和索引都是增量的，只处理变更文件
- **用户驱动** — 哪些对话值得提炼由用户决定，AI 只做建议
- **一次少量** — 每次提炼 1-3 条对话为宜，保证质量
- **通道化存储** — 笔记可以输出到多个通道（local/notion/...），互不干扰
- **状态可追踪** — 每条对话都有明确的提炼状态（pending/done/outdated/skipped）
- **可撤销** — 误操作可用 `reset` 恢复到 pending 状态
