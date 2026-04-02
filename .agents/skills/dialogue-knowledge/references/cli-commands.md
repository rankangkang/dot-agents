# dialogue-kb CLI 命令参考

这份文档用于说明 `dialogue-kb.py` 的命令细节、参数语义和常见组合。

只有在以下场景才需要读取它：

- 需要确认某个命令的具体参数
- 需要向用户解释远程扫描或筛选行为
- 需要解释状态字段、分页、`--channels` 等细节

如果你只需要判断“下一步该做什么”，通常不需要加载这份文档。

## 使用前提

本文假设你已按 SKILL.md 的指引找到脚本真实路径。后文用 `$KB` 代指该绝对路径。

## 命令总览

| 命令 | 用途 |
|------|------|
| `$KB scan [-v] [--local-only] [--remote HOST...]` | 扫描对话文件 |
| `$KB collect [-v] [--local-only] [--remote HOST...]` | 收集对话并重建索引 |
| `$KB index` | 重建索引 |
| `$KB list [QUERY] [--source X] [--host X] [--state X] [--pending] [--days N] [--since DATE] [--offset N] [--limit N]` | 浏览与搜索 |
| `$KB show <ID> [--full]` | 查看对话详情 |
| `$KB triage` | 输出待提炼摘要 JSON |
| `$KB done <ID...> [--channels X] [--note-title X]` | 标记为已提炼 |
| `$KB skip <ID...> [--reason X]` | 标记为跳过 |
| `$KB reset <ID...>` | 恢复为 pending |
| `$KB stats` | 查看统计概览 |

## 收集与扫描

### `scan`

只扫描，不归档，不改索引。适合先看范围和数量。

```bash
$KB scan -v
$KB scan --local-only
$KB scan --remote $REMOTE_HOST
```

### `collect`

把数据收集到归档目录，并在结束后自动重建索引。

```bash
$KB collect -v
$KB collect --local-only
$KB collect --remote $REMOTE_HOST
```

### 远程行为

默认规则：

- 不传 `--remote`，且未加 `--local-only` 时，会处理本机，并尝试 `~/.ssh/config` 中的远程主机
- `--local-only` 表示只处理本机
- `--remote HOST...` 表示只处理指定主机
- `--remote` 后面不跟主机名，等价于“不处理任何远程”

远程操作可能失败或超时。解释结果时要把“无新文件”和“远程失败”区分开，不要混为一谈。

## 浏览与筛选

### `list`

按条件浏览索引中的对话。

```bash
$KB list
$KB list "关键词"
$KB list --pending
$KB list --source cursor
$KB list --host $REMOTE_HOST
$KB list --since 2026-03-10
$KB list --days 7
$KB list --offset 20 --limit 20
```

常用筛选含义：

- `--source`：按工具筛选
- `--host`：按主机筛选
- `--state`：按 `pending/done/outdated/skipped` 筛选
- `--pending`：同时包含 `pending` 和 `outdated`
- `--offset` / `--limit`：分页

### `show`

查看单条对话详情。

```bash
$KB show <ID>
$KB show <ID> --full
```

默认会截断超长内容；只有确实需要看全部文本时才用 `--full`。

### `triage`

输出待提炼对话的紧凑摘要 JSON，适合做第一轮批量筛选。

输出条目通常包含：

- `id`
- `idx`
- `title`
- `first_question`
- `turns`
- `tool`
- `host`
- `project`
- `state`

## 状态命令

### `done`

将一条或多条对话标记为已提炼。

```bash
$KB done <ID...>
$KB done <ID...> --channels "local"
$KB done <ID...> --channels "local,mirror-note" --note-title "笔记标题"
```

注意：

- `--channels` 只是记录“这篇笔记被保存到了哪些通道”的元数据
- 它不会自动执行写入动作
- 额外通道名应来自用户自己的约定，并记录在 `memory.md`
- 若未传 `--channels`，脚本仍会把状态改为 `done`

### `skip`

将一条或多条对话标记为跳过。

```bash
$KB skip <ID...>
$KB skip <ID...> --reason "无实质内容"
```

适合批量处理闲聊、极短、纯命令或明显未完成的对话。

### `reset`

把状态恢复为 `pending`。

```bash
$KB reset <ID...>
```

`reset` 会清掉与提炼结果相关的元数据，如 `channels`、`note_title`、`skip_reason`。

## 状态含义

列表和索引中常见状态：

- `pending`：待提炼
- `done`：已提炼
- `outdated`：已提炼，但对话后续又增长了
- `skipped`：已跳过

若看到 `↑N`，表示这条对话比上次提炼时又多了 `N` 轮，应重新检查新增部分。

## 常见组合

### 第一次整理对话

```bash
$KB collect
$KB triage
$KB show <ID>
$KB done <ID> --channels "local" --note-title "笔记标题"
```

### 只看本机，避免远程

```bash
$KB collect --local-only
$KB list --pending
```

### 按关键词找历史对话

```bash
$KB list "关键词"
$KB show <ID>
```

## 典型误解

- `done` 不会生成或写入笔记。它只是在索引里把状态标成 `done`，并可选记录 `channels`、`note_title` 等元数据。
- `--channels` 不会创建通道，也不会自动把内容同步到某个地方。它只表示“这篇笔记已经被保存到这些通道”。
- `scan` 和 `collect` 不一样。`scan` 只看范围和数量；`collect` 才会把数据收进归档并重建索引。
- `triage` 不是全文阅读。它只输出摘要，适合第一轮筛选；真正要深读时应使用 `show`。
- `reset` 不是“重新收集”。它只把索引状态恢复为 `pending`，不会重新同步文件。
