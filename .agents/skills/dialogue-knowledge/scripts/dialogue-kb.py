#!/usr/bin/env python3
"""dialogue-kb: AI 对话知识库 CLI 工具

从 Cursor / Claude Code / claude-internal / CodeBuddy 等 AI 编程工具中
收集对话记录，解析为统一格式，构建本地知识库索引。

用法:
  dialogue-kb scan   [--remote HOST...]    扫描本地+远程的 AI 对话文件
  dialogue-kb collect [--remote HOST...]   同步远程对话到本地归档
  dialogue-kb index                        解析对话并构建索引
  dialogue-kb list   [--source X] [QUERY]  列出/搜索对话
  dialogue-kb show   <ID>                  查看对话详情
  dialogue-kb stats                        显示统计信息

纯 Python 标准库实现，零依赖。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── 常量 ──

DEFAULT_ARCHIVE_DIR = Path.home() / ".ai-dialogues"
CONFIG_FILE = "config.yaml"
INDEX_FILE = "index.json"

TOOL_DIRS = {
    "cursor": Path.home() / ".cursor",
    "claude": Path.home() / ".claude",
    "claude-internal": Path.home() / ".claude-internal",
    "codebuddy": Path.home() / ".codebuddy",
}

# 用于对话内容预处理时剔除的噪声模式
NOISE_PATTERNS = [
    (re.compile(r"<thinking>[\s\S]*?</thinking>", re.I), ""),
    (re.compile(r"<antml_thinking>[\s\S]*?</antml_thinking>", re.I), ""),
    (re.compile(r"<antml_function_calls>[\s\S]*?</antml_function_calls>", re.I), ""),
    (re.compile(r"<function_calls>[\s\S]*?</function_calls>", re.I), ""),
    (re.compile(r"<tool_use>[\s\S]*?</tool_use>", re.I), ""),
    (re.compile(r"<tool_call>[\s\S]*?</tool_call>", re.I), ""),
    (re.compile(r"<tool_result>[\s\S]*?</tool_result>", re.I), ""),
    (re.compile(r"<rules>[\s\S]*?</rules>", re.I), ""),
    (re.compile(r"<memories>[\s\S]*?</memories>", re.I), ""),
    (re.compile(r"<user_info>[\s\S]*?</user_info>", re.I), ""),
    (re.compile(r"<attached_files>[\s\S]*?</attached_files>", re.I), ""),
    (re.compile(r"<open_and_recently_viewed_files>[\s\S]*?</open_and_recently_viewed_files>", re.I), ""),
    (re.compile(r"<agent_skills>[\s\S]*?</agent_skills>", re.I), ""),
    (re.compile(r"<local-command-caveat>[\s\S]*?</local-command-caveat>", re.I), ""),
    (re.compile(r"<local-command-stdout>[\s\S]*?</local-command-stdout>", re.I), ""),
    (re.compile(r"<command-name>[\s\S]*?</command-name>", re.I), ""),
    (re.compile(r"<command-message>[\s\S]*?</command-message>", re.I), ""),
    (re.compile(r"<command-args>[\s\S]*?</command-args>", re.I), ""),
    (re.compile(r"<system_reminder>[\s\S]*?</system_reminder>", re.I), ""),
    (re.compile(r"<git_status>[\s\S]*?</git_status>", re.I), ""),
]

_SKIP_FOR_TITLE_RE = re.compile(
    r"^(<local-command|<command-|Caveat: The messages below|<system_reminder>)",
    re.I,
)

# ── 颜色输出 ──

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
    lines = [
        f"archive_dir: {config.get('archive_dir', str(archive_dir))}",
        "",
    ]
    if config.get("remotes"):
        lines.append("remotes:")
        for remote in config["remotes"]:
            lines.append(f"  - host: {remote['host']}")
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _parse_simple_yaml(text: str) -> dict:
    """极简 YAML 解析器，只处理本项目用到的扁平结构。"""
    result = {"remotes": []}
    current_remote = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue
        if stripped.startswith("- host:"):
            host = stripped.split(":", 1)[1].strip()
            current_remote = {"host": host}
            result["remotes"].append(current_remote)
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


# ═══════════════════════════════════════
# 扫描：发现对话文件
# ═══════════════════════════════════════

def scan_local() -> dict:
    """扫描本地所有 AI 工具的对话文件。"""
    result = {
        "host": "localhost",
        "sources": [],
        "total_files": 0,
    }

    # Cursor agent-transcripts
    cursor_dir = TOOL_DIRS["cursor"] / "projects"
    if cursor_dir.is_dir():
        count = 0
        projects = []
        for project_dir in cursor_dir.iterdir():
            if not project_dir.is_dir():
                continue
            transcripts_dir = project_dir / "agent-transcripts"
            if not transcripts_dir.is_dir():
                continue
            jsonl_files = list(transcripts_dir.rglob("*.jsonl"))
            parent_files = [f for f in jsonl_files if "subagents" not in str(f)]
            if parent_files:
                project_name = project_dir.name.replace("Users-", "").replace("-", "/")
                projects.append({
                    "name": project_name,
                    "path": str(transcripts_dir),
                    "count": len(parent_files),
                })
                count += len(parent_files)
        if count > 0:
            result["sources"].append({
                "tool": "cursor",
                "type": "agent-transcripts",
                "projects": projects,
                "count": count,
            })
            result["total_files"] += count

    # Claude Code / claude-internal / codebuddy — 统一扫描 projects/ 目录
    for tool_name in ["claude", "claude-internal", "codebuddy"]:
        tool_dir = TOOL_DIRS.get(tool_name)
        if not tool_dir:
            continue
        projects_dir = tool_dir / "projects"
        if not projects_dir.is_dir():
            continue
        jsonl_files = list(projects_dir.rglob("*.jsonl"))
        parent_files = [f for f in jsonl_files if "subagents" not in str(f)]
        if parent_files:
            # 按项目分组
            projects = {}
            for f in parent_files:
                rel = f.relative_to(projects_dir)
                project_name = str(rel.parts[0]) if len(rel.parts) > 1 else "default"
                projects.setdefault(project_name, []).append(f)
            project_list = [
                {"name": name, "path": str(projects_dir / name), "count": len(files)}
                for name, files in sorted(projects.items())
            ]
            result["sources"].append({
                "tool": tool_name,
                "type": "jsonl-sessions",
                "projects": project_list,
                "count": len(parent_files),
            })
            result["total_files"] += len(parent_files)

    # CodeBuddy IDE — directory-based format
    cb_ide_candidates = [
        Path.home() / "Library" / "Application Support" / "CodeBuddyExtension" / "Data",
        Path.home() / ".local" / "share" / "CodeBuddyExtension",
    ]
    for cb_base in cb_ide_candidates:
        if not cb_base.is_dir():
            continue
        try:
            proc = subprocess.run(
                f"find {shlex.quote(str(cb_base))} -maxdepth 10 -type d -name history 2>/dev/null | head -10",
                shell=True, capture_output=True, text=True, timeout=10,
            )
            for hist_dir in proc.stdout.strip().splitlines():
                hist_dir = hist_dir.strip()
                if not hist_dir:
                    continue
                hist_path = Path(hist_dir)
                session_count = sum(1 for p in hist_path.iterdir() if p.is_dir())
                if session_count > 0:
                    result["sources"].append({
                        "tool": "codebuddy-ide",
                        "type": "directory-sessions",
                        "count": session_count,
                        "path": hist_dir,
                    })
                    result["total_files"] += session_count
        except Exception:
            pass

    return result


def scan_remote(host: str, timeout: int = 30) -> dict:
    """通过 SSH 扫描远程主机上的 AI 对话文件。"""
    result = {
        "host": host,
        "sources": [],
        "total_files": 0,
        "error": "",
    }

    combined_cmd = (
        "echo '__CURSOR__';"
        "find ~/.cursor/projects -maxdepth 4 -name '*.jsonl' -path '*/agent-transcripts/*' "
        "! -path '*/subagents/*' 2>/dev/null | head -200;"
        "echo '__CLAUDE__';"
        "find ~/.claude/projects -maxdepth 4 -name '*.jsonl' "
        "! -path '*/subagents/*' 2>/dev/null | head -200;"
        "echo '__CLAUDE_INTERNAL__';"
        "find ~/.claude-internal/projects -maxdepth 4 -name '*.jsonl' "
        "! -path '*/subagents/*' 2>/dev/null | head -200;"
        "echo '__CODEBUDDY__';"
        "find ~/.codebuddy/projects -maxdepth 4 -name '*.jsonl' "
        "! -path '*/subagents/*' 2>/dev/null | head -200;"
        "echo '__END__'"
    )

    try:
        proc = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes", host, combined_cmd],
            capture_output=True, text=True, timeout=timeout,
        )
        if proc.returncode not in (0, 1):
            result["error"] = f"SSH failed (exit {proc.returncode}): {proc.stderr.strip()[:200]}"
            return result

        section = None
        tool_map = {
            "__CURSOR__": "cursor",
            "__CLAUDE__": "claude",
            "__CLAUDE_INTERNAL__": "claude-internal",
            "__CODEBUDDY__": "codebuddy",
        }
        files_by_tool: dict[str, list[str]] = {t: [] for t in tool_map.values()}

        for line in proc.stdout.splitlines():
            line = line.strip()
            if line in tool_map:
                section = tool_map[line]
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
    results = []

    for tool_name, tool_dir in TOOL_DIRS.items():
        projects_dir = tool_dir / "projects"
        if not projects_dir.is_dir():
            continue

        if tool_name == "cursor":
            # Cursor: projects/*/agent-transcripts/*/*.jsonl
            for project_dir in projects_dir.iterdir():
                if not project_dir.is_dir():
                    continue
                transcripts_dir = project_dir / "agent-transcripts"
                if not transcripts_dir.is_dir():
                    continue
                for session_dir in transcripts_dir.iterdir():
                    if not session_dir.is_dir():
                        continue
                    for jsonl_file in session_dir.glob("*.jsonl"):
                        if "subagents" in str(jsonl_file):
                            continue
                        dest = archive_dir / "archive" / "cursor" / project_dir.name / jsonl_file.name
                        _copy_if_newer(jsonl_file, dest)
                        results.append({
                            "tool": "cursor",
                            "project": project_dir.name,
                            "file": jsonl_file.name,
                            "source": str(jsonl_file),
                        })
        else:
            # Claude/claude-internal/codebuddy: projects/**/*.jsonl
            for jsonl_file in projects_dir.rglob("*.jsonl"):
                if "subagents" in str(jsonl_file):
                    continue
                rel = jsonl_file.relative_to(projects_dir)
                project_name = str(rel.parts[0]) if len(rel.parts) > 1 else "default"
                dest = archive_dir / "archive" / tool_name / project_name / jsonl_file.name
                _copy_if_newer(jsonl_file, dest)
                results.append({
                    "tool": tool_name,
                    "project": project_name,
                    "file": jsonl_file.name,
                    "source": str(jsonl_file),
                })

    # CodeBuddy IDE — directory-based sessions
    cb_ide_candidates = [
        Path.home() / "Library" / "Application Support" / "CodeBuddyExtension" / "Data",
        Path.home() / ".local" / "share" / "CodeBuddyExtension",
    ]
    for cb_base in cb_ide_candidates:
        if not cb_base.is_dir():
            continue
        try:
            proc = subprocess.run(
                f"find {shlex.quote(str(cb_base))} -maxdepth 10 -type d -name history 2>/dev/null | head -10",
                shell=True, capture_output=True, text=True, timeout=10,
            )
            for hist_dir in proc.stdout.strip().splitlines():
                hist_dir = hist_dir.strip()
                if not hist_dir:
                    continue
                hist_path = Path(hist_dir)
                for workspace_dir in hist_path.iterdir():
                    if not workspace_dir.is_dir():
                        continue
                    for conv_dir in workspace_dir.iterdir():
                        if not conv_dir.is_dir():
                            continue
                        idx_file = conv_dir / "index.json"
                        if not idx_file.exists():
                            continue
                        # 复制整个会话目录到归档
                        dest_base = archive_dir / "archive" / "codebuddy-ide" / workspace_dir.name / conv_dir.name
                        _copy_dir_if_newer(conv_dir, dest_base)
                        results.append({
                            "tool": "codebuddy-ide",
                            "project": workspace_dir.name,
                            "file": conv_dir.name,
                            "source": str(conv_dir),
                        })
        except Exception:
            pass

    return results


def _copy_dir_if_newer(src_dir: Path, dest_dir: Path):
    """递归复制目录，仅当源文件比目标新时才复制。"""
    import shutil as _shutil
    for src_file in src_dir.rglob("*"):
        if not src_file.is_file():
            continue
        rel = src_file.relative_to(src_dir)
        dest_file = dest_dir / rel
        if dest_file.exists() and dest_file.stat().st_mtime >= src_file.stat().st_mtime:
            continue
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        _shutil.copy2(src_file, dest_file)


def collect_remote(host: str, archive_dir: Path, timeout: int = 180) -> list[dict]:
    """通过 rsync 从远程主机同步对话文件到本地归档。"""
    results = []

    for tool_name in ["cursor", "claude", "claude-internal", "codebuddy"]:
        if tool_name == "cursor":
            remote_path = f"{host}:~/.cursor/projects/"
            local_dir = archive_dir / "archive" / f"{host}" / "cursor"
        else:
            remote_path = f"{host}:~/.{tool_name}/projects/"
            local_dir = archive_dir / "archive" / f"{host}" / tool_name

        local_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            "rsync", "-avz",
            "--include=*/",
            "--include=*.jsonl",
            "--exclude=*",
            "--exclude=subagents/",
            remote_path,
            str(local_dir) + "/",
        ]

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            synced = [l for l in proc.stdout.splitlines() if l.endswith(".jsonl")]
            results.append({
                "host": host,
                "tool": tool_name,
                "status": "success" if proc.returncode == 0 else "error",
                "files_synced": len(synced),
                "message": proc.stderr.strip()[:200] if proc.returncode != 0 else "",
            })
        except subprocess.TimeoutExpired:
            results.append({
                "host": host, "tool": tool_name,
                "status": "error", "files_synced": 0,
                "message": f"Timeout after {timeout}s",
            })
        except Exception as e:
            results.append({
                "host": host, "tool": tool_name,
                "status": "error", "files_synced": 0,
                "message": str(e),
            })

    return results


def _copy_if_newer(src: Path, dest: Path):
    """仅当源文件比目标新时才复制。"""
    if dest.exists() and dest.stat().st_mtime >= src.stat().st_mtime:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy2(src, dest)


# ═══════════════════════════════════════
# 解析：各工具格式 → 统一结构
# ═══════════════════════════════════════

def strip_noise(text: str) -> str:
    """剔除对话内容中的噪声块（thinking/tool_call/system info 等）。"""
    for pattern, replacement in NOISE_PATTERNS:
        text = pattern.sub(replacement, text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_cursor_jsonl(filepath: Path) -> dict | None:
    """解析 Cursor agent-transcripts JSONL 文件。

    格式: 每行一个 JSON, {role: "user"|"assistant", message: {content: [{type, text}]}}
    """
    try:
        lines = filepath.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    except Exception:
        return None

    if not lines:
        return None

    turns = []
    first_user_text = ""
    first_ts = None

    for line in lines:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        role = obj.get("role", "")
        if role not in ("user", "assistant"):
            continue

        content_blocks = obj.get("message", {}).get("content", [])
        text_parts = []
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif isinstance(block, str):
                text_parts.append(block)

        full_text = "\n".join(text_parts).strip()
        if not full_text:
            continue

        # 提取 user_query 标签中的实际问题
        clean_text = full_text
        uq_match = re.search(r"<user_query>([\s\S]*?)</user_query>", full_text)
        if uq_match:
            clean_text = uq_match.group(1).strip()

        clean_text = strip_noise(clean_text)
        if not clean_text:
            continue

        if role == "user" and not first_user_text:
            first_user_text = clean_text[:200]

        turns.append({"role": role, "text": clean_text})

    if len(turns) < 2:
        return None

    session_id = filepath.stem
    return {
        "id": session_id,
        "source": "cursor",
        "file": str(filepath),
        "title": _extract_title(first_user_text),
        "first_question": first_user_text,
        "turn_count": len(turns),
        "user_turns": sum(1 for t in turns if t["role"] == "user"),
        "assistant_turns": sum(1 for t in turns if t["role"] == "assistant"),
        "turns": turns,
    }


def parse_claude_jsonl(filepath: Path) -> dict | None:
    """解析 Claude Code / claude-internal JSONL 文件。

    格式: 每行一个 JSON, {type: "user"|"assistant"|..., message: {content: ...}, timestamp: ...}
    """
    try:
        lines = filepath.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    except Exception:
        return None

    if not lines:
        return None

    turns = []
    first_user_text = ""
    first_ts = None
    session_id = filepath.stem
    cwd = ""

    for line in lines:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        if not isinstance(obj, dict):
            continue

        msg_type = obj.get("type", "")
        if msg_type not in ("user", "assistant"):
            continue

        # 跳过 sidechain 消息
        if obj.get("isSidechain"):
            continue

        if not first_ts and obj.get("timestamp"):
            first_ts = obj["timestamp"]
        if not cwd and obj.get("cwd"):
            cwd = obj["cwd"]

        message = obj.get("message", {})
        content = message.get("content", "")

        text_parts = []
        if isinstance(content, str):
            text_parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)

        full_text = "\n".join(text_parts).strip()
        clean_text = strip_noise(full_text)
        if not clean_text:
            continue

        if msg_type == "user" and not first_user_text:
            if not _SKIP_FOR_TITLE_RE.match(clean_text):
                uq_match = re.search(r"<user_query>([\s\S]*?)</user_query>", clean_text)
                if uq_match:
                    first_user_text = uq_match.group(1).strip()[:200]
                else:
                    first_user_text = clean_text[:200]

        turns.append({"role": msg_type, "text": clean_text})

    if len(turns) < 2:
        return None

    return {
        "id": session_id,
        "source": "claude",
        "file": str(filepath),
        "title": _extract_title(first_user_text),
        "first_question": first_user_text,
        "turn_count": len(turns),
        "user_turns": sum(1 for t in turns if t["role"] == "user"),
        "assistant_turns": sum(1 for t in turns if t["role"] == "assistant"),
        "timestamp": first_ts,
        "cwd": cwd,
        "turns": turns,
    }


def parse_codebuddy_jsonl(filepath: Path) -> dict | None:
    """解析 CodeBuddy JSONL 文件。

    格式: 每行一个 JSON, {type: "message", role: "user"|"assistant",
          content: [{type: "input_text"|"output_text"|"text", text: "..."}]}
    """
    try:
        lines = filepath.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    except Exception:
        return None

    if not lines:
        return None

    turns = []
    first_user_text = ""
    first_ts = None
    cwd = ""

    for line in lines:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        if not isinstance(obj, dict):
            continue

        role = obj.get("role", "")
        if role not in ("user", "assistant"):
            continue

        if not first_ts and obj.get("timestamp"):
            first_ts = obj["timestamp"]
        if not cwd and obj.get("cwd"):
            cwd = obj["cwd"]

        content = obj.get("content", [])
        text_parts = []
        if isinstance(content, str):
            text_parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    block_type = block.get("type", "")
                    if block_type in ("text", "input_text", "output_text"):
                        text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)

        full_text = "\n".join(text_parts).strip()

        # 跳过系统/命令消息
        if full_text.startswith("Caveat: The messages below"):
            continue
        if "<command-name>" in full_text and len(full_text) < 200:
            continue
        if "<local-command-stdout>" in full_text and len(full_text) < 200:
            continue

        clean_text = strip_noise(full_text)
        if not clean_text:
            continue

        if role == "user" and not first_user_text:
            if not _SKIP_FOR_TITLE_RE.match(clean_text):
                uq_match = re.search(r"<user_query>([\s\S]*?)</user_query>", clean_text)
                if uq_match:
                    first_user_text = uq_match.group(1).strip()[:200]
                else:
                    first_user_text = clean_text[:200]

        turns.append({"role": role, "text": clean_text})

    if len(turns) < 2:
        return None

    return {
        "id": filepath.stem,
        "source": "codebuddy",
        "file": str(filepath),
        "title": _extract_title(first_user_text),
        "first_question": first_user_text,
        "turn_count": len(turns),
        "user_turns": sum(1 for t in turns if t["role"] == "user"),
        "assistant_turns": sum(1 for t in turns if t["role"] == "assistant"),
        "timestamp": first_ts,
        "cwd": cwd,
        "turns": turns,
    }


def parse_codebuddy_ide_session(conv_dir: Path) -> dict | None:
    """解析 CodeBuddy IDE 的目录结构会话。

    目录布局:
      conv_dir/
        index.json          — 消息列表（有序）+ requests
        messages/
          {msg_id}.json     — 单条消息文件
    """
    index_path = conv_dir / "index.json"
    if not index_path.exists():
        return None

    try:
        index = json.loads(index_path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None

    msg_list = index.get("messages", [])
    if not msg_list:
        return None

    requests = index.get("requests", [])
    first_ts = None
    if requests:
        try:
            started = requests[0].get("startedAt")
            if isinstance(started, (int, float)):
                first_ts = datetime.fromtimestamp(started / 1000, tz=timezone.utc).isoformat()
        except Exception:
            pass

    msg_files = {}
    msgs_dir = conv_dir / "messages"
    if msgs_dir.is_dir():
        for f in msgs_dir.iterdir():
            if f.suffix == ".json":
                msg_files[f.stem] = f

    turns = []
    first_user_text = ""

    for msg_meta in msg_list:
        msg_id = msg_meta.get("id", "")
        role = msg_meta.get("role", "")
        if role not in ("user", "assistant"):
            continue

        msg_file = msg_files.get(msg_id)
        if not msg_file:
            continue
        try:
            raw = json.loads(msg_file.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue

        msg_body = raw.get("message", "")
        if isinstance(msg_body, str):
            try:
                msg_body = json.loads(msg_body)
            except Exception:
                continue

        content_blocks = msg_body.get("content", [])
        if not isinstance(content_blocks, list):
            continue

        text_parts = []
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text", ""))

        full_text = "\n".join(text_parts).strip()
        clean_text = strip_noise(full_text)
        if not clean_text:
            continue

        if role == "user" and not first_user_text:
            if not _SKIP_FOR_TITLE_RE.match(clean_text):
                uq_match = re.search(r"<user_query>([\s\S]*?)</user_query>", clean_text)
                if uq_match:
                    first_user_text = uq_match.group(1).strip()[:200]
                else:
                    first_user_text = clean_text[:200]

        turns.append({"role": role, "text": clean_text})

    if len(turns) < 2:
        return None

    return {
        "id": conv_dir.name,
        "source": "codebuddy-ide",
        "file": str(conv_dir),
        "title": _extract_title(first_user_text),
        "first_question": first_user_text,
        "turn_count": len(turns),
        "user_turns": sum(1 for t in turns if t["role"] == "user"),
        "assistant_turns": sum(1 for t in turns if t["role"] == "assistant"),
        "timestamp": first_ts,
        "turns": turns,
    }


def _extract_title(text: str) -> str:
    """从用户第一条消息中提取简短标题。"""
    if not text:
        return "Untitled"
    clean = text.strip().split("\n")[0]
    clean = re.sub(r"[#*`@]", "", clean).strip()
    if len(clean) > 80:
        clean = clean[:77] + "..."
    return clean or "Untitled"


# ═══════════════════════════════════════
# 索引构建
# ═══════════════════════════════════════

def _file_fingerprint(filepath: Path) -> str:
    """生成文件指纹（mtime + size），用于检测变更。"""
    try:
        st = filepath.stat()
        return f"{st.st_mtime:.6f}:{st.st_size}"
    except Exception:
        return ""


def _dir_fingerprint(dirpath: Path) -> str:
    """生成目录指纹（所有文件的 mtime + size 组合哈希），用于检测变更。"""
    parts = []
    try:
        for f in sorted(dirpath.rglob("*")):
            if f.is_file():
                st = f.stat()
                parts.append(f"{f.name}:{st.st_mtime:.6f}:{st.st_size}")
    except Exception:
        pass
    return hashlib.md5("|".join(parts).encode()).hexdigest()[:12] if parts else ""


def _apply_distill_state(entry: dict, old: dict | None, new_turn_count: int):
    """根据旧条目的状态和新的 turn_count，决定提炼状态。

    状态流转:
      新条目                          → pending
      旧条目未变                      → 保持原状态
      旧条目 pending + 对话增长       → pending（还没提炼过，增长不影响）
      旧条目 done   + 对话增长       → outdated（提炼过了但有新内容）
      旧条目 done   + 对话未增长     → done
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

    # 传递已有的提炼元数据
    if old.get("distilled_at"):
        entry["distilled_at"] = old["distilled_at"]
    if old.get("note_file"):
        entry["note_file"] = old["note_file"]


def build_index(archive_dir: Path) -> dict:
    """增量构建索引。

    对比已有索引中的文件指纹，仅重新解析变更/新增的文件。
    保留已有条目的 distill_state 等状态字段。
    """
    archive_path = archive_dir / "archive"
    if not archive_path.is_dir():
        return {"conversations": [], "built_at": datetime.now(timezone.utc).isoformat(),
                "stats": {"new": 0, "updated": 0, "unchanged": 0, "removed": 0}}

    # 加载已有索引，构建 id → entry 映射
    index_path = archive_dir / INDEX_FILE
    old_entries = {}
    if index_path.exists():
        try:
            old_index = json.loads(index_path.read_text(encoding="utf-8"))
            for e in old_index.get("conversations", []):
                old_entries[e["id"]] = e
        except Exception:
            pass

    conversations = []
    seen_ids = set()
    stats = {"new": 0, "updated": 0, "unchanged": 0, "removed": 0}

    # ── JSONL 类型（Cursor / Claude / claude-internal / CodeBuddy 插件）──
    for jsonl_file in sorted(archive_path.rglob("*.jsonl")):
        if "subagents" in str(jsonl_file):
            continue

        rel = jsonl_file.relative_to(archive_path)
        parts = rel.parts
        if len(parts) < 2:
            continue

        tool_name = _detect_tool_from_path(parts)
        if tool_name not in ("cursor", "codebuddy", "claude", "claude-internal"):
            continue

        conv_id = jsonl_file.stem
        if conv_id in seen_ids:
            continue
        seen_ids.add(conv_id)

        fingerprint = _file_fingerprint(jsonl_file)
        old = old_entries.get(conv_id)

        # 指纹未变 → 直接复用旧条目
        if old and old.get("_fingerprint") == fingerprint:
            conversations.append(old)
            stats["unchanged"] += 1
            continue

        # 指纹变了或新文件 → 重新解析
        if tool_name == "cursor":
            parsed = parse_cursor_jsonl(jsonl_file)
        elif tool_name == "codebuddy":
            parsed = parse_codebuddy_jsonl(jsonl_file)
        else:
            parsed = parse_claude_jsonl(jsonl_file)

        if not parsed:
            continue

        host, project = _extract_host_project(parts)

        entry = {
            "id": conv_id,
            "source": parsed["source"],
            "tool": tool_name,
            "file": str(jsonl_file),
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
        stats["updated" if old else "new"] += 1
        conversations.append(entry)

    # ── CodeBuddy IDE（目录结构）──
    cb_ide_archive = archive_path / "codebuddy-ide"
    if cb_ide_archive.is_dir():
        for workspace_dir in cb_ide_archive.iterdir():
            if not workspace_dir.is_dir():
                continue
            for conv_dir in workspace_dir.iterdir():
                if not conv_dir.is_dir():
                    continue
                if not (conv_dir / "index.json").exists():
                    continue

                conv_id = conv_dir.name
                if conv_id in seen_ids:
                    continue
                seen_ids.add(conv_id)

                fingerprint = _dir_fingerprint(conv_dir)
                old = old_entries.get(conv_id)

                if old and old.get("_fingerprint") == fingerprint:
                    conversations.append(old)
                    stats["unchanged"] += 1
                    continue

                parsed = parse_codebuddy_ide_session(conv_dir)
                if not parsed:
                    continue

                entry = {
                    "id": conv_id,
                    "source": "codebuddy-ide",
                    "tool": "codebuddy-ide",
                    "file": str(conv_dir),
                    "title": parsed["title"],
                    "first_question": parsed["first_question"],
                    "turn_count": parsed["turn_count"],
                    "user_turns": parsed["user_turns"],
                    "assistant_turns": parsed["assistant_turns"],
                    "host": "localhost",
                    "project": workspace_dir.name,
                    "_fingerprint": fingerprint,
                }
                if parsed.get("timestamp"):
                    entry["timestamp"] = parsed["timestamp"]

                _apply_distill_state(entry, old, parsed["turn_count"])
                stats["updated" if old else "new"] += 1
                conversations.append(entry)

    # 统计被删除的条目
    stats["removed"] = len(set(old_entries.keys()) - seen_ids)

    # 按时间戳排序
    conversations.sort(
        key=lambda c: c.get("timestamp", c.get("id", "")),
        reverse=True,
    )

    index = {
        "conversations": conversations,
        "total": len(conversations),
        "built_at": datetime.now(timezone.utc).isoformat(),
        "stats": stats,
    }

    archive_dir.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    return index


def _detect_tool_from_path(parts: tuple) -> str:
    """从归档路径推断工具类型。"""
    for p in parts:
        if p in ("cursor", "claude", "claude-internal", "codebuddy"):
            return p
        if "cursor" in p.lower():
            return "cursor"
        if "claude-internal" in p.lower():
            return "claude-internal"
        if "claude" in p.lower():
            return "claude"
        if "codebuddy" in p.lower():
            return "codebuddy"
    return "unknown"


def _extract_host_project(parts: tuple) -> tuple[str, str]:
    """从归档路径推断主机名和项目名。"""
    if parts[0] in ("cursor", "claude", "claude-internal", "codebuddy"):
        host = "localhost"
        project = parts[1] if len(parts) > 1 else "unknown"
    else:
        host = parts[0]
        project = parts[2] if len(parts) > 2 else parts[1] if len(parts) > 1 else "unknown"
    return host, project


# ═══════════════════════════════════════
# CLI 命令实现
# ═══════════════════════════════════════

def cmd_scan(args):
    """扫描本地和远程的 AI 对话文件。"""
    print(bold("扫描 AI 对话文件...\n"))

    # 本地扫描
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

    # 远程扫描
    hosts = args.remote or []
    if not hosts and args.all_remotes:
        hosts = load_ssh_hosts()

    for host in hosts:
        print(f"  {green(host)} ", end="", flush=True)
        remote = scan_remote(host)
        if remote["error"]:
            print(f"{red('✗')} {remote['error']}")
        elif remote["sources"]:
            print()
            for src in remote["sources"]:
                tool_label = _tool_display(src["tool"])
                print(f"    {tool_label}: {cyan(str(src['count']))} 条对话")
        else:
            print(f"{dim('无对话文件')}")

    total = local["total_files"] + sum(
        scan_remote(h).get("total_files", 0) for h in hosts
    ) if hosts else local["total_files"]
    print(f"\n{bold('总计')}: {total} 条对话文件")


def cmd_collect(args):
    """收集对话文件到本地归档。"""
    archive_dir = Path(args.archive_dir)
    print(bold(f"收集对话到 {archive_dir}/archive/\n"))

    # 本地收集
    print(f"  {green('localhost')} ... ", end="", flush=True)
    local_results = collect_local(archive_dir)
    tools_count = {}
    for r in local_results:
        tools_count[r["tool"]] = tools_count.get(r["tool"], 0) + 1
    if tools_count:
        parts = [f"{_tool_display(t)}: {c}" for t, c in sorted(tools_count.items())]
        print(", ".join(parts))
    else:
        print(dim("无新文件"))

    # 远程收集
    hosts = args.remote or []
    for host in hosts:
        print(f"  {green(host)} ... ", end="", flush=True)
        remote_results = collect_remote(host, archive_dir)
        parts = []
        for r in remote_results:
            if r["files_synced"] > 0:
                parts.append(f"{_tool_display(r['tool'])}: {r['files_synced']}")
        if parts:
            print(", ".join(parts))
        else:
            print(dim("无新文件"))

    # 构建索引
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

    # 显示
    limit = args.limit or 20
    for i, conv in enumerate(conversations[:limit]):
        idx = dim(f"[{i+1}]")
        tool = _tool_display(conv.get("tool", "?"))
        title = conv.get("title", "Untitled")
        turns = dim(f"({conv.get('turn_count', '?')} turns)")
        host = dim(f"@{conv.get('host', '?')}")
        state = conv.get("distill_state", "")
        state_tag = ""
        if state == "done":
            state_tag = green(" ✔")
        elif state == "outdated":
            prev = conv.get("_prev_turn_count", "?")
            state_tag = yellow(f" ↑{conv.get('turn_count',0)-prev if isinstance(prev,int) else '?'}")
        elif state == "pending":
            state_tag = dim(" ·")

        print(f"  {idx} {tool} {bold(title)} {turns} {host}{state_tag}")

    if len(conversations) > limit:
        print(f"\n  {dim(f'... 共 {len(conversations)} 条，已显示前 {limit} 条')}")


def cmd_show(args):
    """查看对话详情。"""
    archive_dir = Path(args.archive_dir)
    index_path = archive_dir / INDEX_FILE

    if not index_path.exists():
        print(yellow("索引不存在，请先运行: dialogue-kb collect"))
        return

    index = json.loads(index_path.read_text(encoding="utf-8"))
    conversations = index.get("conversations", [])

    # 按编号或 ID 查找
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

    # 解析并显示完整对话
    filepath = Path(conv["file"])
    if not filepath.exists():
        print(red(f"文件不存在: {filepath}"))
        return

    tool = conv.get("tool", "unknown")
    if tool == "cursor":
        parsed = parse_cursor_jsonl(filepath)
    elif tool == "codebuddy-ide":
        parsed = parse_codebuddy_ide_session(filepath)
    elif tool == "codebuddy":
        parsed = parse_codebuddy_jsonl(filepath)
    else:
        parsed = parse_claude_jsonl(filepath)

    if not parsed:
        print(red("解析失败"))
        return

    print(bold(f"\n{'═' * 60}"))
    print(bold(f"  {parsed['title']}"))
    print(f"  {_tool_display(tool)} | {dim(conv.get('host', '?'))} | {parsed['turn_count']} turns")
    print(bold(f"{'═' * 60}\n"))

    for turn in parsed["turns"]:
        role_label = green("  User") if turn["role"] == "user" else blue("  AI")
        print(f"{role_label}:")
        text = turn["text"]
        if len(text) > 2000:
            text = text[:1000] + f"\n{dim('... [truncated] ...')}\n" + text[-500:]
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

    # 提炼状态
    by_state = {}
    for c in conversations:
        s = c.get("distill_state", "pending")
        by_state[s] = by_state.get(s, 0) + 1
    state_labels = {"pending": "待提炼", "done": "已提炼", "outdated": "有更新", "skipped": "已跳过"}
    state_parts = []
    for s in ["pending", "outdated", "done", "skipped"]:
        if by_state.get(s):
            state_parts.append(f"{state_labels.get(s, s)}: {by_state[s]}")
    if state_parts:
        print(f"  提炼状态: {', '.join(state_parts)}")

    # 按工具统计
    by_tool = {}
    for c in conversations:
        t = c.get("tool", "unknown")
        by_tool[t] = by_tool.get(t, 0) + 1
    print(f"\n  {bold('按工具:')}")
    for tool, count in sorted(by_tool.items(), key=lambda x: -x[1]):
        print(f"    {_tool_display(tool)}: {count}")

    # 按主机统计
    by_host = {}
    for c in conversations:
        h = c.get("host", "unknown")
        by_host[h] = by_host.get(h, 0) + 1
    print(f"\n  {bold('按主机:')}")
    for host, count in sorted(by_host.items(), key=lambda x: -x[1]):
        print(f"    {host}: {count}")

    # 按项目统计（前 10）
    by_project = {}
    for c in conversations:
        p = c.get("project", "unknown")
        by_project[p] = by_project.get(p, 0) + 1
    print(f"\n  {bold('按项目 (Top 10):')}")
    for project, count in sorted(by_project.items(), key=lambda x: -x[1])[:10]:
        print(f"    {project}: {count}")

    print()


def _tool_display(tool: str) -> str:
    labels = {
        "cursor": cyan("▶ Cursor"),
        "claude": green("◆ Claude"),
        "claude-internal": green("◆ claude-internal"),
        "codebuddy": yellow("★ CodeBuddy"),
        "codebuddy-ide": yellow("★ CodeBuddy IDE"),
    }
    return labels.get(tool, tool)


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
    p_scan.add_argument("--remote", nargs="*", help="远程 SSH 主机名")
    p_scan.add_argument("--all-remotes", action="store_true", help="扫描 ~/.ssh/config 中所有主机")
    p_scan.add_argument("-v", "--verbose", action="store_true")

    # collect
    p_collect = sub.add_parser("collect", help="收集对话到本地归档")
    p_collect.add_argument("--remote", nargs="*", help="远程 SSH 主机名")

    # index
    sub.add_parser("index", help="重建索引")

    # list
    p_list = sub.add_parser("list", help="列出/搜索对话")
    p_list.add_argument("query", nargs="?", help="搜索关键词")
    p_list.add_argument("--source", help="按工具筛选 (cursor/claude/claude-internal/codebuddy)")
    p_list.add_argument("--host", help="按主机筛选")
    p_list.add_argument("--limit", type=int, default=20, help="显示条数 (默认 20)")

    # show
    p_show = sub.add_parser("show", help="查看对话详情")
    p_show.add_argument("id", help="对话编号或 ID")

    # stats
    sub.add_parser("stats", help="显示统计信息")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    commands = {
        "scan": cmd_scan,
        "collect": cmd_collect,
        "index": cmd_index,
        "list": cmd_list,
        "show": cmd_show,
        "stats": cmd_stats,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
