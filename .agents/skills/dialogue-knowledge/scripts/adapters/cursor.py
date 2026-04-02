"""adapters/cursor.py — Cursor agent-transcripts 适配器。

格式: projects/*/agent-transcripts/*/*.jsonl
每行一个 JSON: {role: "user"|"assistant", message: {content: [{type, text}]}}
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .base import (
    KNOWN_TOOL_DIRS,
    ToolAdapter,
    USER_QUERY_RE,
    extract_title,
    strip_noise,
)


class CursorAdapter(ToolAdapter):
    """Cursor IDE agent-transcripts 适配器。"""

    tool_name = "cursor"
    label = "▶ Cursor"

    # ── 本地发现 ──────────────────────────────────────────────────────────────

    def local_sessions(self) -> list[tuple[Path, str]]:
        sessions: list[tuple[Path, str]] = []
        projects_dir = Path.home() / ".cursor" / "projects"
        if not projects_dir.is_dir():
            return []
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
                    if "subagents" not in str(jsonl_file):
                        sessions.append((jsonl_file, project_dir.name))
        return sessions

    # ── 归档 ──────────────────────────────────────────────────────────────────

    def copy_to_archive(self, src: Path, project: str, archive_dir: Path) -> Path:
        dest = archive_dir / "archive" / "cursor" / project / src.name
        self._copy_file_if_newer(src, dest)
        return dest

    def _sessions_under_cursor_root(self, cursor_root: Path, host: str) -> list[tuple[Path, str, str]]:
        """兼容两种归档布局。

        本机归档是扁平布局:
          archive/cursor/{project}/{id}.jsonl

        远程 rsync 归档会保留 Cursor 原始目录层级:
          archive/{host}/cursor/{project}/agent-transcripts/{session}/{id}.jsonl
        """
        sessions: list[tuple[Path, str, str]] = []
        seen: set[Path] = set()
        if not cursor_root.is_dir():
            return sessions

        for project_dir in sorted(cursor_root.iterdir()):
            if not project_dir.is_dir():
                continue

            for jsonl_file in sorted(project_dir.glob("*.jsonl")):
                if "subagents" in str(jsonl_file) or jsonl_file in seen:
                    continue
                sessions.append((jsonl_file, project_dir.name, host))
                seen.add(jsonl_file)

            transcripts_dir = project_dir / "agent-transcripts"
            if not transcripts_dir.is_dir():
                continue
            for session_dir in sorted(transcripts_dir.iterdir()):
                if not session_dir.is_dir():
                    continue
                for jsonl_file in sorted(session_dir.glob("*.jsonl")):
                    if "subagents" in str(jsonl_file) or jsonl_file in seen:
                        continue
                    sessions.append((jsonl_file, project_dir.name, host))
                    seen.add(jsonl_file)
        return sessions

    def archive_sessions(self, archive_dir: Path) -> list[tuple[Path, str, str]]:
        out = self._sessions_under_cursor_root(
            archive_dir / "archive" / "cursor", "localhost"
        )
        archive = archive_dir / "archive"
        if archive.is_dir():
            for host_dir in sorted(archive.iterdir()):
                if not host_dir.is_dir() or host_dir.name in KNOWN_TOOL_DIRS:
                    continue
                out.extend(
                    self._sessions_under_cursor_root(
                        host_dir / "cursor", host_dir.name
                    )
                )
        return out

    # ── 解析 ──────────────────────────────────────────────────────────────────

    def parse(self, path: Path) -> dict | None:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        except Exception:
            return None
        if not lines:
            return None

        turns: list[dict] = []
        first_user_text = ""

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

            # 优先提取 <user_query> 标签内的实际问题
            clean_text = full_text
            uq_match = USER_QUERY_RE.search(full_text)
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

        try:
            file_ts = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
        except Exception:
            file_ts = None

        return {
            "id": path.stem,
            "source": "cursor",
            "file": str(path),
            "title": extract_title(first_user_text),
            "first_question": first_user_text,
            "turn_count": len(turns),
            "user_turns": sum(1 for t in turns if t["role"] == "user"),
            "assistant_turns": sum(1 for t in turns if t["role"] == "assistant"),
            "timestamp": file_ts,
            "turns": turns,
        }

    # ── 远程 ──────────────────────────────────────────────────────────────────

    def remote_section_marker(self) -> str:
        return "__CURSOR__"

    def remote_find_cmd(self) -> str:
        return (
            "find ~/.cursor/projects -maxdepth 4 -name '*.jsonl'"
            " -path '*/agent-transcripts/*' ! -path '*/subagents/*'"
            " 2>/dev/null | head -200"
        )

    def remote_rsync(self, host: str, archive_dir: Path) -> tuple[str, Path]:
        return (
            f"{host}:~/.cursor/projects/",
            archive_dir / "archive" / host / "cursor",
        )
