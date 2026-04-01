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

找到后用绝对路径调用，后续示例中用 `$KB` 代替完整路径；`$REMOTE_HOST` 表示 `~/.ssh/config` 中的 Host 名（按需替换，可多传）。

## 读取记忆

本 SKILL 通过记忆文件（`memory.md`）持久化用户偏好。记忆文件位于 SKILL 同目录下，用 Glob 查找：

```
**/skills/dialogue-knowledge/memory.md
```

**启动时：** 如果记忆文件存在，先读取内容，后续操作遵循其中的偏好（如默认存储通道、启用的数据源等）。如果不存在，按默认行为执行。

**记忆内容**是自然语言，用户和 AI 都可以编辑，典型内容包括：

- 笔记存储通道偏好 — 默认用哪些通道，配置后不再每次询问
- 数据源配置 — 启用/禁用哪些 AI 工具，自定义数据源的位置和格式
- 提炼偏好 — 每次处理多少条、语言偏好、关注领域等
- 写作风格偏好 — 偏案例复盘 / 偏通用方法论 / 先案例后抽象 / 长文或卡片式
- 敏感信息处理偏好 — 是否默认脱敏、是否保留项目名/路径/内部系统名、是否优先泛化表达
- 任何其他个性化设置

**更新记忆：** 当用户在对话中表达新偏好时（如"以后都存到 Notion"、"不要扫描 claude-internal"），主动提议更新记忆文件。确认后用 Write 工具写入完整的 `memory.md`。

尤其是当用户对**笔记写作风格**提出反馈时，应优先考虑把它沉淀为长期偏好，而不是只在本次会话里临时遵循。例如：

- “以后尽量写成通用方法论，不要只复盘项目改动”
- “默认脱敏，去掉项目名和内部系统名”
- “我更喜欢长文展开，不要太卡片化”
- “先给结论，再展开分析”

**首次使用引导：** 如果记忆文件不存在，在完成首次提炼后建议建立偏好——问用户笔记存到哪里、用哪些 AI 工具、有没有特殊偏好，然后生成 `memory.md`。

首次使用引导时，除了存储通道和数据源，也可以顺带询问用户是否有**写作风格偏好**，例如：

- 更偏案例复盘还是通用方法论
- 是否默认脱敏 / 泛化表达
- 喜欢短笔记还是中长篇展开

## 快速开始

如果用户第一次使用，或者说了"帮我整理对话"但没指定具体操作，按以下流程一条龙走完：

0. 读取 `memory.md`（如果存在），了解用户偏好
1. `$KB collect` — 收集对话到归档（默认本机 + `~/.ssh/config` 中的全部 Host；仅本机可加 `--local-only`）
2. `$KB triage` — 获取待提炼对话摘要
3. 从 triage 结果中挑出 3-5 条最有价值的（标题有明确技术内容的），展示给用户
4. 用户选择后，逐条 `$KB show` + 提炼 + `$KB done`
5. 首次使用且无 `memory.md` 时，流程结束后引导用户建立记忆

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

### 2. 收集与扫描（本机 + 远程默认全开）

**默认行为（重要）：** `scan` / `collect` 在**不传 `--remote` 且未加 `--local-only`** 时，会在本机之外，继续对 **`~/.ssh/config` 里列出的所有 Host**（不含 `*` 通配）逐个尝试 SSH 扫描或 rsync。这样一次命令即可覆盖常用开发机。

**不要远程、只处理本机：**

```bash
$KB scan --local-only -v
$KB collect --local-only
```

**只指定若干台远程（覆盖默认「全部 Host」）：**

```bash
$KB collect --remote $REMOTE_HOST -v
$KB scan --remote $REMOTE_HOST
```

多台远程时在 `--remote` 后依次追加更多 Host 名。

**显式不要任何远程（与 `--local-only` 等价于「零远程」的另一种写法）：** 使用 `--remote` 但不跟主机名（空列表）：

```bash
$KB collect --remote
```

**输出：** 每次 `scan` / `collect` 开头会打印一行 **「扫描范围 / 收集范围」**，标明本机与远程主机策略。`--all-remotes` 已废弃，与默认行为相同（保留仅为兼容旧命令）。

**`list` / `show` / `triage`：** 每条对话都带有 **主机（host）** 与 **归档项目目录（project）**。`list` 在每行以 `@主机 / 项目` 形式展示来源；有筛选条件时会先打印 **「列表筛选」** 一行；`triage` 的 JSON 里除 `tool`、`host` 外还有 **`project`** 字段。

**未接入 CLI 的配置：** `~/.ai-dialogues/config.yaml` 中的 `remotes` 等字段**目前不会被** `scan`/`collect` 自动读取；远程列表仅来自「默认 SSH Host」或命令行 `--remote`。

```bash
# 先看本机+远程各有多少文件（加 -v 可看按项目明细）
$KB scan -v

# 收集到本地归档（增量；默认含全部 SSH Host）
$KB collect -v

# 仅本机、最快
$KB collect --local-only
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

输出 JSON 格式，每条包含 `id`、`title`、`first_question`、`turns`、`tool`、`host`、`project`。**不含对话全文**，数据量很小。

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

以下是**默认写作原则**。若 `memory.md` 中存在明确的写作风格、敏感信息处理或抽象层级偏好，应优先遵循；若用户在当前对话中有更明确的新要求，则以本次要求为最高优先级。

- 写给一个月后的自己——开头 1-2 句话就让人知道这篇在讲什么
- 让内容决定结构，不要硬套模板——需要标题就加，不需要就别加
- 重点写反直觉的、容易忘的、容易踩坑的，不写常识
- 代码只保留不查文档就想不起来的关键片段
- 不要复述对话过程，不要面面俱到——只留最有价值的部分
- 一条对话生成一篇笔记

##### 写作风格可配置（通过 `memory.md`）

写作风格不应被固定为单一模板，允许用户通过自然语言在 `memory.md` 中声明偏好。Agent 读取后，应在提炼时主动调整笔记形态，而不是机械套用默认风格。

常见可配置维度包括：

- **抽象层级** — 偏案例复盘、偏通用方法论、先案例后抽象、只保留结论
- **结构偏好** — 卡片式、短文式、长文分析式、结论先行、问题驱动
- **语气偏好** — 偏理性分析、偏经验总结、偏写给未来自己的备忘
- **代码细节保留程度** — 少代码重结论、保留关键片段、尽量不出现具体实现
- **敏感信息处理** — 默认脱敏、弱化项目背景、泛化内部系统名、避免暴露路径/人名/库名

推荐遵循以下优先级：

1. 当前用户消息中的明确要求
2. `memory.md` 中的长期偏好
3. 本节默认写作原则

若记忆中要求“优先泛化表达”或“默认去敏”，提炼时应主动把项目名、内部系统名、目录路径、人员信息等替换为通用表述；除非这些细节对知识本身不可或缺。

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

**执行顺序：** 如果记忆中配置了默认通道，直接使用，无需每次询问；否则询问用户想存到哪些通道（可多选）。然后逐个执行。

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
$KB list --host $REMOTE_HOST    # 按主机（与 SSH Host 名大小写不敏感）
$KB list --pending              # 只看待提炼的
$KB list --days 7               # 最近一周
$KB list --since 2026-03-10     # 某日之后
$KB list --offset 20            # 翻页（跳过前 20 条）
$KB stats                       # 统计概览
```

每行格式：`[序号] 工具图标 @主机 / 项目 标题 (turns) 状态`。

列表中每条对话末尾的状态标记：
- `·` = pending（待提炼）
- `✔` = done（已提炼）
- `↑N` = outdated（已提炼但新增了 N 轮对话）
- 无标记 = skipped

## 命令速查

| 命令 | 说明 |
|------|------|
| `$KB scan [-v] [--local-only] [--remote HOST...]` | 扫描；默认含 `~/.ssh/config` 全部 Host |
| `$KB collect [-v] [--local-only] [--remote HOST...]` | 收集到归档；远程规则同 `scan` |
| `$KB index` | 重建索引 |
| `$KB list [QUERY] [--source X] [--host X] [--state X] [--pending] [--days N] [--since DATE] [--offset N] [--limit N]` | 列出/搜索对话 |
| `$KB show <ID> [--full]` | 查看对话详情 |
| `$KB triage` | 输出待提炼摘要(JSON) |
| `$KB done <ID...> [--channels X] [--note-title X]` | 标记为已提炼 |
| `$KB skip <ID...> [--reason X]` | 标记为跳过 |
| `$KB reset <ID...>` | 重置状态为 pending |
| `$KB stats` | 统计概览 |

## 关键原则

- **记忆驱动** — 通过 `memory.md` 持久化用户偏好，减少重复询问，支持个性化工作流
- **增量优先** — 收集和索引都是增量的，只处理变更文件
- **远程默认全开** — `scan`/`collect` 默认会连 `~/.ssh/config` 中全部 Host；常用 `--local-only` 加快或避免无效连接
- **用户驱动** — 哪些对话值得提炼由用户决定，AI 只做建议
- **一次少量** — 每次提炼 1-3 条对话为宜，保证质量
- **通道化存储** — 笔记可以输出到多个通道（local/notion/...），互不干扰
- **状态可追踪** — 每条对话都有明确的提炼状态（pending/done/outdated/skipped）
- **可撤销** — 误操作可用 `reset` 恢复到 pending 状态
