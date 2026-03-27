#!/usr/bin/env python3
"""dialogue-kb: AI 对话知识库 CLI 工具

从 Cursor / Claude Code / claude-internal / CodeBuddy 等 AI 编程工具中
收集对话记录，解析为统一格式，构建本地知识库索引。

用法:
  dialogue-kb scan   [--local-only] [--remote HOST...]   扫描本机；默认再扫 ~/.ssh/config 中全部 Host
  dialogue-kb collect [--local-only] [--remote HOST...]  收集到归档；远程规则同 scan
  dialogue-kb index                        解析对话并构建索引
  dialogue-kb list   [--source X] [QUERY]  列出/搜索对话
  dialogue-kb show   <ID> [--full]         查看对话详情
  dialogue-kb triage                       输出待提炼摘要(JSON)
  dialogue-kb done   <ID...>               标记为已提炼（支持批量）
  dialogue-kb skip   <ID...>               标记为跳过（支持批量）
  dialogue-kb reset  <ID...>               重置状态为 pending
  dialogue-kb stats                        显示统计信息

纯 Python 标准库实现，零依赖。
新增工具：在 adapters/ 目录下添加一个 Adapter 类，无需修改本文件。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── 加载 adapters 包 ─────────────────────────────────────────────────────────
# 将本文件所在目录加入 sys.path，使 `from adapters import ...` 可用
sys.path.insert(0, str(Path(__file__).parent))
from adapters import ADAPTER_BY_NAME, ADAPTERS  # noqa: E402

# ── 常量 ─────────────────────────────────────────────────────────────────────

DEFAULT_ARCHIVE_DIR = Path.home() / ".ai-dialogues"
CONFIG_FILE = "config.yaml"
INDEX_FILE = "index.json"

# ── 颜色输出 ─────────────────────────────────────────────────────────────────


def _c(code, text):
    if sys.stdout.isatty():
        return f"\033[{code}m{text}\033[0m"
    return text


def green(t):  return _c("32", t)
def yellow(t): return _c("33", t)
def blue(t):   return _c("34", t)
def cyan(t):   return _c("36", t)
def dim(t):    return _c("2", t)
def red(t):    return _c("31", t)
def bold(t):   return _c("1", t)


_verbose = False


def _warn(msg: str):
    if _verbose:
        print(f"  {dim(f'[warn] {msg}')}", file=sys.stderr)


# ═══════════════════════════════════════
# 配置
# ═══════════════════════════════════════

def load_config(archive_dir: Path) -> dict:
    config_path = archive_dir / CONFIG_FILE
    if not config_path.exists():
        return {"archive_dir": str(archive_dir), "remotes": []}
    text = config_path.read_text(encoding="utf-8")
    return _parse_simple_yaml(text)


def save_config(archive_dir: Path, config: dict):
    config_path = archive_dir / CONFIG_FILE
    archive_dir.mkdir(parents=True, exist_ok=True)
    lines = [f"archive_dir: {config.get('archive_dir', str(archive_dir))}", ""]
    if config.get("remotes"):
        lines.append("remotes:")
        for remote in config["remotes"]:
            lines.append(f"  - host: {remote['host']}")
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _parse_simple_yaml(text: str) -> dict:
    """极简 YAML 解析器，只处理本项目用到的扁平结构。"""
    result = {"remotes": []}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue
        if stripped.startswith("- host:"):
            host = stripped.split(":", 1)[1].strip()
            result["remotes"].append({"host": host})
        elif not line.startswith(" ") and ":" in stripped:
            key, val = stripped.split(":", 1)
            result[key.strip()] = val.strip()
    return result


# ═══════════════════════════════════════
# SSH 配置读取
# ═══════════════════════════════════════

def load_ssh_hosts() -> list[str]:
    ssh_config = Path.home() / ".ssh" / "config"
    if not ssh_config.exists():
        return []
    hosts = []
    for line in ssh_config.read_text().splitlines():
        line = line.strip()
        if line.lower().startswith("host ") and "*" not in line:
            for h in line.split()[1:]:
                if h and not h.startswith("#"):
                    hosts.append(h)
    return sorted(set(hosts))


def resolve_remote_hosts(args) -> tuple[list[str], str]:
    """解析 scan/collect 使用的远程主机列表及人类可读的范围说明。

    规则:
      - --local-only → 不连远程
      - 显式传入 --remote A B → 仅这些主机（``--remote`` 无参数等价于空列表，不连远程）
      - 默认 → ~/.ssh/config 中全部 Host（不含通配符）
    """
    if getattr(args, "local_only", False):
        return [], "无（已 --local-only）"
    explicit = getattr(args, "remote", None)
    if explicit is not None:
        if explicit:
            return list(explicit), f"指定 {len(explicit)} 台: {', '.join(explicit)}"
        return [], "无（已 --remote 且未列主机名）"
    hosts = load_ssh_hosts()
    if not hosts:
        return [], "无（~/.ssh/config 中无可用 Host 条目）"
    return hosts, f"SSH 配置全部 Host（{len(hosts)} 台）: {', '.join(hosts)}"


def _short_label(text: str, max_len: int = 42) -> str:
    """列表中项目名等过长时截断。"""
    t = (text or "").strip() or "—"
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


# ═══════════════════════════════════════
# 扫描：发现对话文件
# ═══════════════════════════════════════

def scan_local() -> dict:
    """扫描本地所有 AI 工具的对话文件（通过各 Adapter 发现）。"""
    result: dict = {"host": "localhost", "sources": [], "total_files": 0}

    for adapter in ADAPTERS:
        sessions = adapter.local_sessions()
        if not sessions:
            continue
        projects: dict[str, int] = {}
        for _, project in sessions:
            projects[project] = projects.get(project, 0) + 1
        result["sources"].append({
            "tool": adapter.tool_name,
            "count": len(sessions),
            "projects": [{"name": k, "count": v} for k, v in sorted(projects.items())],
        })
        result["total_files"] += len(sessions)

    return result


def scan_remote(host: str, timeout: int = 30) -> dict:
    """通过 SSH 扫描远程主机上的 AI 对话文件。"""
    result: dict = {"host": host, "sources": [], "total_files": 0, "error": ""}

    # 从支持远程扫描的 Adapter 组装合并 SSH 命令
    cmd_parts: list[str] = []
    marker_to_tool: dict[str, str] = {}
    for adapter in ADAPTERS:
        marker = adapter.remote_section_marker()
        if not marker:
            continue
        cmd_parts.append(f"echo '{marker}';")
        cmd_parts.append(adapter.remote_find_cmd() + ";")
        marker_to_tool[marker] = adapter.tool_name
    cmd_parts.append("echo '__END__'")
    combined_cmd = " ".join(cmd_parts)

    try:
        proc = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes", host, combined_cmd],
            capture_output=True, text=True, timeout=timeout,
        )
        if proc.returncode not in (0, 1):
            result["error"] = f"SSH failed (exit {proc.returncode}): {proc.stderr.strip()[:200]}"
            return result

        section = None
        files_by_tool: dict[str, list[str]] = {t: [] for t in marker_to_tool.values()}

        for line in proc.stdout.splitlines():
            line = line.strip()
            if line in marker_to_tool:
                section = marker_to_tool[line]
            elif line == "__END__":
                break
            elif section and line:
                files_by_tool[section].append(line)

        for tool_name, files in files_by_tool.items():
            if files:
                result["sources"].append({
                    "tool": tool_name,
                    "count": len(files),
                    "sample_paths": files[:3],
                })
                result["total_files"] += len(files)

    except subprocess.TimeoutExpired:
        result["error"] = f"SSH timeout after {timeout}s"
    except Exception as e:
        result["error"] = str(e)

    return result


# ═══════════════════════════════════════
# 收集：同步到本地归档
# ═══════════════════════════════════════

def collect_local(archive_dir: Path) -> list[dict]:
    """收集本地 AI 工具的对话文件到归档目录。"""
    results: list[dict] = []
    for adapter in ADAPTERS:
        for src, project in adapter.local_sessions():
            adapter.copy_to_archive(src, project, archive_dir)
            results.append({
                "tool": adapter.tool_name,
                "project": project,
                "file": src.name,  # 文件名或会话目录名（CodeBuddy IDE 为目录）
                "source": str(src),
            })
    return results


def collect_remote(host: str, archive_dir: Path, timeout: int = 180) -> list[dict]:
    """通过 rsync 从远程主机同步对话文件到本地归档。"""
    results: list[dict] = []

    for adapter in ADAPTERS:
        rsync_info = adapter.remote_rsync(host, archive_dir)
        if not rsync_info:
            continue
        remote_src, local_dir = rsync_info
        local_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            "rsync", "-avz",
            "--include=*/",
            "--include=*.jsonl",
            "--exclude=*",
            "--exclude=subagents/",
            remote_src,
            str(local_dir) + "/",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            synced = [l for l in proc.stdout.splitlines() if l.endswith(".jsonl")]
            results.append({
                "host": host,
                "tool": adapter.tool_name,
                "status": "success" if proc.returncode == 0 else "error",
                "files_synced": len(synced),
                "message": proc.stderr.strip()[:200] if proc.returncode != 0 else "",
            })
        except subprocess.TimeoutExpired:
            results.append({
                "host": host, "tool": adapter.tool_name,
                "status": "error", "files_synced": 0,
                "message": f"Timeout after {timeout}s",
            })
        except Exception as e:
            results.append({
                "host": host, "tool": adapter.tool_name,
                "status": "error", "files_synced": 0,
                "message": str(e),
            })

    return results


# ═══════════════════════════════════════
# 索引构建
# ═══════════════════════════════════════

def _apply_distill_state(entry: dict, old: dict | None, new_turn_count: int):
    """根据旧条目的状态和新的 turn_count，决定提炼状态。

    状态流转:
      新条目                          → pending
      旧条目未变                      → 保持原状态
      旧条目 pending + 对话增长       → pending（还没提炼过，增长不影响）
      旧条目 done   + 对话增长        → outdated（提炼过了但有新内容）
      旧条目 done   + 对话未增长      → done
      旧条目 skipped                  → skipped
    """
    if not old:
        entry["distill_state"] = "pending"
        return

    old_state = old.get("distill_state", "pending")
    old_turns = old.get("turn_count", 0)

    if old_state == "done" and new_turn_count > old_turns:
        entry["distill_state"] = "outdated"
        entry["_prev_turn_count"] = old_turns
    else:
        entry["distill_state"] = old_state

    for field in ("distilled_at", "note_file", "channels", "note_title", "skip_reason"):
        if old.get(field):
            entry[field] = old[field]


_COMMAND_TITLE_RE = re.compile(
    r"^(/model|/plugin|/help|/config|/quit|/exit|resume$|<local-command|<command-)",
    re.I,
)


def _compute_worth(entry: dict) -> str:
    """基于客观指标预过滤，只做脚本能确定的判断。

    返回:
      "auto_skip"  — 确定无价值（太短 / 无回复 / 纯命令）
      "normal"     — 需要 AI 判断（脚本无法确定价值）
    """
    turns = entry.get("turn_count", 0)
    user_turns = entry.get("user_turns", 0)
    asst_turns = entry.get("assistant_turns", 0)
    title = entry.get("title", "")
    first_q = entry.get("first_question", "")

    if turns < 2:
        return "auto_skip"
    if asst_turns == 0:
        return "auto_skip"
    if user_turns == 0:
        return "auto_skip"
    if _COMMAND_TITLE_RE.match(first_q):
        return "auto_skip"
    if title in ("Untitled", "") and turns < 4:
        return "auto_skip"

    return "normal"


def _timestamp_sort_value(ts) -> float:
    """将异构时间戳（ISO 字符串、Unix 秒/毫秒）规范为可比较的秒数。"""
    if ts is None:
        return 0.0
    if isinstance(ts, (int, float)):
        v = float(ts)
        return v / 1000.0 if v > 1e11 else v
    if isinstance(ts, str):
        s = ts.strip()
        if not s:
            return 0.0
        try:
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            return 0.0
    return 0.0


def _conversation_sort_key(c: dict) -> tuple[float, str]:
    """新到旧排序；同时间戳用 id 稳定排序。"""
    return (-_timestamp_sort_value(c.get("timestamp")), str(c.get("id") or ""))


def build_index(archive_dir: Path) -> dict:
    """增量构建索引。

    通过各 Adapter 的 archive_sessions() 枚举归档，仅重新解析变更/新增的文件。
    保留已有条目的 distill_state 等状态字段。
    """
    archive_path = archive_dir / "archive"
    if not archive_path.is_dir():
        return {
            "conversations": [],
            "built_at": datetime.now(timezone.utc).isoformat(),
            "stats": {"new": 0, "updated": 0, "unchanged": 0, "removed": 0},
        }

    index_path = archive_dir / INDEX_FILE
    old_entries: dict[str, dict] = {}
    if index_path.exists():
        try:
            old_index = json.loads(index_path.read_text(encoding="utf-8"))
            for e in old_index.get("conversations", []):
                old_entries[e["id"]] = e
        except Exception:
            pass

    conversations: list[dict] = []
    seen_ids: set[str] = set()
    stats = {"new": 0, "updated": 0, "unchanged": 0, "removed": 0}

    for adapter in ADAPTERS:
        for path, project, host in adapter.archive_sessions(archive_dir):
            conv_id = path.stem if path.is_file() else path.name
            if conv_id in seen_ids:
                continue
            seen_ids.add(conv_id)

            fingerprint = adapter.fingerprint(path)
            old = old_entries.get(conv_id)

            # 指纹未变 → 直接复用旧条目
            if old and old.get("_fingerprint") == fingerprint:
                conversations.append(old)
                stats["unchanged"] += 1
                continue

            parsed = adapter.parse(path)
            if not parsed:
                continue

            entry: dict = {
                "id": conv_id,
                "source": parsed.get("source", adapter.tool_name),
                "tool": adapter.tool_name,
                "file": str(path),
                "title": parsed["title"],
                "first_question": parsed["first_question"],
                "turn_count": parsed["turn_count"],
                "user_turns": parsed["user_turns"],
                "assistant_turns": parsed["assistant_turns"],
                "host": host,
                "project": project,
                "_fingerprint": fingerprint,
            }
            if parsed.get("timestamp"):
                entry["timestamp"] = parsed["timestamp"]
            if parsed.get("cwd"):
                entry["cwd"] = parsed["cwd"]

            _apply_distill_state(entry, old, parsed["turn_count"])
            entry["worth"] = _compute_worth(entry)
            if entry["worth"] == "auto_skip" and entry.get("distill_state") == "pending":
                entry["distill_state"] = "skipped"
                entry["skip_reason"] = "auto: too short or system command"
            stats["updated" if old else "new"] += 1
            conversations.append(entry)

    # 对缓存命中的旧条目补算 worth
    for conv in conversations:
        if "worth" not in conv:
            conv["worth"] = _compute_worth(conv)
            if conv["worth"] == "auto_skip" and conv.get("distill_state") == "pending":
                conv["distill_state"] = "skipped"
                conv["skip_reason"] = "auto: too short or system command"

    stats["removed"] = len(set(old_entries.keys()) - seen_ids)
    conversations.sort(key=_conversation_sort_key)

    index = {
        "conversations": conversations,
        "total": len(conversations),
        "built_at": datetime.now(timezone.utc).isoformat(),
        "stats": stats,
    }
    archive_dir.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return index


# ═══════════════════════════════════════
# CLI 命令实现
# ═══════════════════════════════════════

def _tool_display(tool: str) -> str:
    """返回带颜色的工具显示标签。"""
    adapter = ADAPTER_BY_NAME.get(tool)
    if not adapter:
        return tool
    color_fns = {
        "cursor": cyan,
        "claude": green,
        "claude-internal": green,
        "codebuddy": yellow,
        "codebuddy-ide": yellow,
    }
    return color_fns.get(tool, lambda x: x)(adapter.label)


def _print_index_stats(index: dict):
    s = index.get("stats", {})
    total = index.get("total", 0)
    parts = [f"{green(str(total))} 条对话"]
    detail = []
    if s.get("new"):
        detail.append(f"{green(str(s['new']))} 新增")
    if s.get("updated"):
        detail.append(f"{yellow(str(s['updated']))} 更新")
    if s.get("unchanged"):
        detail.append(f"{dim(str(s['unchanged']))} 未变")
    if s.get("removed"):
        detail.append(f"{red(str(s['removed']))} 删除")
    if detail:
        parts.append(f"({', '.join(detail)})")
    print(" ".join(parts))


def cmd_scan(args):
    """扫描本地和远程的 AI 对话文件。"""
    hosts, remote_scope = resolve_remote_hosts(args)
    print(bold("扫描 AI 对话文件...\n"))
    print(dim(f"  扫描范围: 本机 localhost；远程 — {remote_scope}"))
    print()

    local = scan_local()
    print(f"  {green('localhost')}")
    if local["sources"]:
        for src in local["sources"]:
            tool_label = _tool_display(src["tool"])
            print(f"    {tool_label}: {cyan(str(src['count']))} 条对话")
            if args.verbose:
                for proj in src.get("projects", []):
                    print(f"      {dim(proj['name'])}: {proj['count']}")
    else:
        print(f"    {dim('未发现对话文件')}")
    print()

    remote_files_total = 0
    for host in hosts:
        print(f"  {green(host)} ", end="", flush=True)
        remote = scan_remote(host)
        remote_files_total += remote.get("total_files", 0)
        if remote["error"]:
            print(f"{red('✗')} {remote['error']}")
        elif remote["sources"]:
            print()
            for src in remote["sources"]:
                print(f"    {_tool_display(src['tool'])}: {cyan(str(src['count']))} 条对话")
        else:
            print(f"{dim('无对话文件')}")

    total = local["total_files"] + remote_files_total
    print(f"\n{bold('总计')}: {total} 条对话文件")


def cmd_collect(args):
    """收集对话文件到本地归档。"""
    archive_dir = Path(args.archive_dir)
    hosts, remote_scope = resolve_remote_hosts(args)
    print(bold(f"收集对话到 {archive_dir}/archive/\n"))
    print(dim(f"  收集范围: 本机 localhost；远程 — {remote_scope}"))
    print()

    print(f"  {green('localhost')} ... ", end="", flush=True)
    local_results = collect_local(archive_dir)
    tools_count: dict[str, int] = {}
    for r in local_results:
        tools_count[r["tool"]] = tools_count.get(r["tool"], 0) + 1
    if tools_count:
        parts = [f"{_tool_display(t)}: {c}" for t, c in sorted(tools_count.items())]
        print(", ".join(parts))
    else:
        print(dim("无新文件"))

    for host in hosts:
        print(f"  {green(host)} ... ", end="", flush=True)
        remote_results = collect_remote(host, archive_dir)
        parts = [
            f"{_tool_display(r['tool'])}: {r['files_synced']}"
            for r in remote_results if r["files_synced"] > 0
        ]
        print(", ".join(parts) if parts else dim("无新文件"))

    print(f"\n  构建索引 ... ", end="", flush=True)
    index = build_index(archive_dir)
    _print_index_stats(index)


def cmd_index(args):
    """重建索引。"""
    archive_dir = Path(args.archive_dir)
    print(bold("构建索引...\n"))
    index = build_index(archive_dir)
    _print_index_stats(index)
    print(f"  索引文件: {archive_dir / INDEX_FILE}")


def cmd_list(args):
    """列出/搜索对话。"""
    archive_dir = Path(args.archive_dir)
    index_path = archive_dir / INDEX_FILE

    if not index_path.exists():
        print(yellow("索引不存在，请先运行: dialogue-kb collect"))
        return

    index = json.loads(index_path.read_text(encoding="utf-8"))
    conversations = index.get("conversations", [])

    # 筛选
    if args.source:
        conversations = [c for c in conversations if c.get("tool") == args.source]
    if args.host:
        conversations = [c for c in conversations if c.get("host") == args.host]
    if args.state:
        conversations = [c for c in conversations if c.get("distill_state") == args.state]
    if args.pending:
        conversations = [c for c in conversations
                         if c.get("distill_state") in ("pending", "outdated")]

    # 时间过滤
    since_dt = None
    if getattr(args, "since", None):
        try:
            since_dt = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
        except ValueError:
            print(red(f"无效日期格式: {args.since}，请用 YYYY-MM-DD"))
            return
    elif getattr(args, "days", None):
        since_dt = datetime.now(timezone.utc) - timedelta(days=args.days)

    if since_dt:
        since_threshold = since_dt.timestamp()
        conversations = [
            c for c in conversations
            if _timestamp_sort_value(c.get("timestamp")) >= since_threshold
        ]

    if args.query:
        q = args.query.lower()
        conversations = [
            c for c in conversations
            if q in c.get("title", "").lower()
            or q in c.get("first_question", "").lower()
        ]

    if not conversations:
        print(dim("未找到匹配的对话"))
        return

    filter_bits = []
    if args.source:
        filter_bits.append(f"工具={args.source}")
    if args.host:
        filter_bits.append(f"主机={args.host}")
    if args.state:
        filter_bits.append(f"状态={args.state}")
    if args.pending:
        filter_bits.append("待提炼")
    if getattr(args, "since", None):
        filter_bits.append(f"since={args.since}")
    if getattr(args, "days", None):
        filter_bits.append(f"近 {args.days} 天")
    if args.query:
        filter_bits.append(f"关键词={args.query!r}")
    if filter_bits:
        print(dim("  列表筛选: " + " · ".join(filter_bits)))
        print()

    total_count = len(conversations)
    offset = getattr(args, "offset", 0) or 0
    limit = args.limit or 20
    page = conversations[offset:offset + limit]

    if not page:
        print(dim(f"偏移 {offset} 超出范围（共 {total_count} 条）"))
        return

    for i, conv in enumerate(page):
        display_idx = offset + i + 1
        idx = dim(f"[{display_idx}]")
        tool = _tool_display(conv.get("tool", "?"))
        title = conv.get("title", "Untitled")
        turns = dim(f"({conv.get('turn_count', '?')} turns)")
        host = conv.get("host", "?")
        proj = _short_label(conv.get("project") or "—")
        origin = dim(f"@{host} / {proj}")

        state = conv.get("distill_state", "")
        state_tag = ""
        if state == "done":
            state_tag = green(" ✔")
        elif state == "outdated":
            prev = conv.get("_prev_turn_count", "?")
            state_tag = yellow(f" ↑{conv.get('turn_count', 0) - prev if isinstance(prev, int) else '?'}")
        elif state == "pending":
            state_tag = dim(" ·")

        print(f"  {idx} {tool} {origin} {bold(title)} {turns}{state_tag}")

    if offset + limit < total_count:
        next_offset = offset + limit
        print(f"\n  {dim(f'共 {total_count} 条，当前 {offset+1}-{offset+len(page)}。下一页: --offset {next_offset}')}")


def cmd_show(args):
    """查看对话详情。"""
    archive_dir = Path(args.archive_dir)
    index_path = archive_dir / INDEX_FILE

    if not index_path.exists():
        print(yellow("索引不存在，请先运行: dialogue-kb collect"))
        return

    index = json.loads(index_path.read_text(encoding="utf-8"))
    conversations = index.get("conversations", [])

    target = args.id
    conv = None
    if target.isdigit():
        idx = int(target) - 1
        if 0 <= idx < len(conversations):
            conv = conversations[idx]
    else:
        conv = next((c for c in conversations if c["id"] == target), None)

    if not conv:
        print(red(f"未找到对话: {target}"))
        return

    filepath = Path(conv["file"])
    if not filepath.exists():
        print(red(f"文件不存在: {filepath}"))
        return

    tool = conv.get("tool", "unknown")
    adapter = ADAPTER_BY_NAME.get(tool)
    if not adapter:
        print(red(f"未知工具类型: {tool}"))
        return

    parsed = adapter.parse(filepath)
    if not parsed:
        print(red("解析失败"))
        return

    print(bold(f"\n{'═' * 60}"))
    print(bold(f"  {parsed['title']}"))
    proj = conv.get("project") or "—"
    print(
        f"  {_tool_display(tool)} | "
        f"{dim('主机:')} {conv.get('host', '?')} | "
        f"{dim('项目:')} {proj} | "
        f"{parsed['turn_count']} turns"
    )
    print(bold(f"{'═' * 60}\n"))

    full_mode = getattr(args, "full", False)
    for turn in parsed["turns"]:
        role_label = green("  User") if turn["role"] == "user" else blue("  AI")
        print(f"{role_label}:")
        text = turn["text"]
        if not full_mode and len(text) > 2000:
            text = text[:1000] + f"\n{dim('... [truncated, use --full to see all] ...')}\n" + text[-500:]
        for line in text.split("\n"):
            print(f"    {line}")
        print()


def cmd_stats(args):
    """显示统计信息。"""
    archive_dir = Path(args.archive_dir)
    index_path = archive_dir / INDEX_FILE

    if not index_path.exists():
        print(yellow("索引不存在，请先运行: dialogue-kb collect"))
        return

    index = json.loads(index_path.read_text(encoding="utf-8"))
    conversations = index.get("conversations", [])

    print(bold("\n对话知识库统计\n"))
    print(f"  总对话数: {green(str(len(conversations)))}")
    print(f"  索引时间: {dim(index.get('built_at', '?'))}")

    by_state: dict[str, int] = {}
    for c in conversations:
        s = c.get("distill_state", "pending")
        by_state[s] = by_state.get(s, 0) + 1
    state_labels = {"pending": "待提炼", "done": "已提炼", "outdated": "有更新", "skipped": "已跳过"}
    state_parts = [
        f"{state_labels.get(s, s)}: {by_state[s]}"
        for s in ["pending", "outdated", "done", "skipped"]
        if by_state.get(s)
    ]
    if state_parts:
        print(f"  提炼状态: {', '.join(state_parts)}")

    by_tool: dict[str, int] = {}
    for c in conversations:
        t = c.get("tool", "unknown")
        by_tool[t] = by_tool.get(t, 0) + 1
    print(f"\n  {bold('按工具:')}")
    for tool, count in sorted(by_tool.items(), key=lambda x: -x[1]):
        print(f"    {_tool_display(tool)}: {count}")

    by_host: dict[str, int] = {}
    for c in conversations:
        h = c.get("host", "unknown")
        by_host[h] = by_host.get(h, 0) + 1
    print(f"\n  {bold('按主机:')}")
    for host, count in sorted(by_host.items(), key=lambda x: -x[1]):
        print(f"    {host}: {count}")

    by_project: dict[str, int] = {}
    for c in conversations:
        p = c.get("project", "unknown")
        by_project[p] = by_project.get(p, 0) + 1
    print(f"\n  {bold('按项目 (Top 10):')}")
    for project, count in sorted(by_project.items(), key=lambda x: -x[1])[:10]:
        print(f"    {project}: {count}")

    print()


def cmd_triage(args):
    """输出待提炼对话的摘要，供 AI 批量判值。

    输出紧凑的 JSON 数组，每条包含 id、title、first_question、turns、tool、host、project，
    方便 AI 一次性扫描并决定哪些值得深入阅读。
    """
    archive_dir = Path(args.archive_dir)
    index_path = archive_dir / INDEX_FILE

    if not index_path.exists():
        print(yellow("索引不存在，请先运行: dialogue-kb collect"))
        return

    index = json.loads(index_path.read_text(encoding="utf-8"))
    conversations = index.get("conversations", [])
    pending = [c for c in conversations if c.get("distill_state") in ("pending", "outdated")]

    if not pending:
        print(json.dumps({"pending": 0, "items": []}, ensure_ascii=False))
        return

    items = [
        {
            "id": c["id"],
            "idx": conversations.index(c) + 1,
            "title": c.get("title", "")[:100],
            "first_question": c.get("first_question", "")[:150],
            "turns": c.get("turn_count", 0),
            "tool": c.get("tool", ""),
            "host": c.get("host", ""),
            "project": c.get("project", ""),
            "state": c.get("distill_state", ""),
        }
        for c in pending
    ]
    print(json.dumps({"pending": len(items), "items": items}, ensure_ascii=False, indent=2))


# ═══════════════════════════════════════
# 提炼状态管理
# ═══════════════════════════════════════

def _update_index_entries(archive_dir: Path, updates_map: dict[str, dict]) -> list[str]:
    """批量更新 index.json 中多条对话的字段。返回成功更新的 ID 列表。"""
    index_path = archive_dir / INDEX_FILE
    if not index_path.exists():
        return []
    index = json.loads(index_path.read_text(encoding="utf-8"))
    updated = []
    for conv in index["conversations"]:
        if conv["id"] in updates_map:
            conv.update(updates_map[conv["id"]])
            updated.append(conv["id"])
    if updated:
        index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return updated


def _resolve_conv_ids(archive_dir: Path, targets: list[str]) -> list[str]:
    """将多个编号或 ID 批量解析为 conv_id 列表。"""
    index_path = archive_dir / INDEX_FILE
    if not index_path.exists():
        return []
    index = json.loads(index_path.read_text(encoding="utf-8"))
    conversations = index.get("conversations", [])
    all_ids = {c["id"] for c in conversations}
    resolved = []
    for target in targets:
        if target.isdigit():
            idx = int(target) - 1
            if 0 <= idx < len(conversations):
                resolved.append(conversations[idx]["id"])
        elif target in all_ids:
            resolved.append(target)
    return resolved


def cmd_done(args):
    """标记对话为已提炼（支持批量）。"""
    archive_dir = Path(args.archive_dir)
    conv_ids = _resolve_conv_ids(archive_dir, args.ids)
    if not conv_ids:
        print(red(f"未找到对话: {', '.join(args.ids)}"))
        return

    channels = [c.strip() for c in args.channels.split(",")] if args.channels else []
    now = datetime.now(timezone.utc).isoformat()
    updates_map = {}
    for cid in conv_ids:
        entry_updates: dict = {"distill_state": "done", "distilled_at": now}
        if channels:
            entry_updates["channels"] = channels
        if args.note_title:
            entry_updates["note_title"] = args.note_title
        updates_map[cid] = entry_updates

    updated = _update_index_entries(archive_dir, updates_map)
    ch_info = f" → {', '.join(channels)}" if channels else ""
    for cid in updated:
        print(green(f"✔ done: {cid}{ch_info}"))
    for cid in set(conv_ids) - set(updated):
        print(red(f"更新失败: {cid}"))


def cmd_skip(args):
    """标记对话为跳过（支持批量）。"""
    archive_dir = Path(args.archive_dir)
    conv_ids = _resolve_conv_ids(archive_dir, args.ids)
    if not conv_ids:
        print(red(f"未找到对话: {', '.join(args.ids)}"))
        return

    now = datetime.now(timezone.utc).isoformat()
    updates_map = {}
    for cid in conv_ids:
        entry_updates: dict = {"distill_state": "skipped", "distilled_at": now}
        if args.reason:
            entry_updates["skip_reason"] = args.reason
        updates_map[cid] = entry_updates

    updated = _update_index_entries(archive_dir, updates_map)
    for cid in updated:
        print(dim(f"⊘ skipped: {cid}"))
    for cid in set(conv_ids) - set(updated):
        print(red(f"更新失败: {cid}"))


def cmd_reset(args):
    """重置对话状态为 pending（支持批量）。"""
    archive_dir = Path(args.archive_dir)
    conv_ids = _resolve_conv_ids(archive_dir, args.ids)
    if not conv_ids:
        print(red(f"未找到对话: {', '.join(args.ids)}"))
        return

    updates_map = {
        cid: {
            "distill_state": "pending",
            "distilled_at": None,
            "skip_reason": None,
            "channels": None,
            "note_title": None,
        }
        for cid in conv_ids
    }
    updated = _update_index_entries(archive_dir, updates_map)
    for cid in updated:
        print(yellow(f"↺ reset to pending: {cid}"))
    for cid in set(conv_ids) - set(updated):
        print(red(f"更新失败: {cid}"))


# ═══════════════════════════════════════
# 主入口
# ═══════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        prog="dialogue-kb",
        description="AI 对话知识库工具",
    )
    parser.add_argument(
        "--archive-dir", default=str(DEFAULT_ARCHIVE_DIR),
        help=f"归档目录 (默认: {DEFAULT_ARCHIVE_DIR})",
    )

    sub = parser.add_subparsers(dest="command", help="子命令")

    # scan
    p_scan = sub.add_parser("scan", help="扫描 AI 对话文件")
    p_scan.add_argument("--local-only", action="store_true", help="仅本机，不通过 SSH 扫远程")
    p_scan.add_argument(
        "--remote", nargs="*", default=None, metavar="HOST",
        help="仅扫描这些 SSH 主机；不写主机名则不扫远程。默认扫 ~/.ssh/config 中全部 Host",
    )
    p_scan.add_argument("--all-remotes", action="store_true",
                        help="已废弃：与默认行为相同（默认即会扫全部 SSH Host）")
    p_scan.add_argument("-v", "--verbose", action="store_true")

    # collect
    p_collect = sub.add_parser("collect", help="收集对话到本地归档")
    p_collect.add_argument("--local-only", action="store_true", help="仅本机，不从远程 rsync")
    p_collect.add_argument(
        "--remote", nargs="*", default=None, metavar="HOST",
        help="仅从所列主机同步；不写主机名则不同步远程。默认同步 ~/.ssh/config 中全部 Host",
    )
    p_collect.add_argument("--all-remotes", action="store_true", help="已废弃：与默认行为相同")
    p_collect.add_argument("-v", "--verbose", action="store_true")

    # index
    sub.add_parser("index", help="重建索引")

    # list
    p_list = sub.add_parser("list", help="列出/搜索对话")
    p_list.add_argument("query", nargs="?", help="搜索关键词")
    p_list.add_argument("--source", help="按工具筛选 (cursor/claude/claude-internal/codebuddy)")
    p_list.add_argument("--host", help="按主机筛选")
    p_list.add_argument("--state", help="按提炼状态筛选 (pending/done/outdated/skipped)")
    p_list.add_argument("--pending", action="store_true", help="仅显示待提炼 (pending + outdated)")
    p_list.add_argument("--limit", type=int, default=20, help="显示条数 (默认 20)")
    p_list.add_argument("--offset", type=int, default=0, help="跳过前 N 条 (分页)")
    p_list.add_argument("--since", help="只显示此日期之后的对话 (YYYY-MM-DD)")
    p_list.add_argument("--days", type=int, help="只显示最近 N 天的对话")

    # show
    p_show = sub.add_parser("show", help="查看对话详情")
    p_show.add_argument("id", help="对话编号或 ID")
    p_show.add_argument("--full", action="store_true", help="显示完整对话，不截断")

    # stats
    sub.add_parser("stats", help="显示统计信息")

    # triage
    sub.add_parser("triage", help="输出待提炼对话摘要 (JSON)，供 AI 批量判值")

    # done
    p_done = sub.add_parser("done", help="标记对话为已提炼（支持批量）")
    p_done.add_argument("ids", nargs="+", help="对话编号或 ID（可传多个）")
    p_done.add_argument("--channels", help="存储通道 (逗号分隔, 如 notion,local)")
    p_done.add_argument("--note-title", help="笔记标题")

    # skip
    p_skip = sub.add_parser("skip", help="标记对话为跳过（支持批量）")
    p_skip.add_argument("ids", nargs="+", help="对话编号或 ID（可传多个）")
    p_skip.add_argument("--reason", help="跳过原因")

    # reset
    p_reset = sub.add_parser("reset", help="重置对话状态为 pending（支持批量）")
    p_reset.add_argument("ids", nargs="+", help="对话编号或 ID（可传多个）")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    global _verbose
    _verbose = getattr(args, "verbose", False)

    commands = {
        "scan": cmd_scan,
        "collect": cmd_collect,
        "index": cmd_index,
        "list": cmd_list,
        "show": cmd_show,
        "stats": cmd_stats,
        "triage": cmd_triage,
        "done": cmd_done,
        "skip": cmd_skip,
        "reset": cmd_reset,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
