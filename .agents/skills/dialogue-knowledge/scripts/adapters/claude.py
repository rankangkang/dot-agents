"""adapters/claude.py — Claude Code / claude-internal 适配器。

两者格式完全相同，仅数据目录不同（~/.claude vs ~/.claude-internal）。
格式: projects/**/*.jsonl
每行: {type: "user"|"assistant", message: {content: ...}, timestamp: ...}
"""
from __future__ import annotations

import json
from pathlib import Path

from .base import (
    ToolAdapter,
    SKIP_FOR_TITLE_RE,
    USER_QUERY_RE,
    extract_title,
    strip_noise,
)


class _ClaudeBaseAdapter(ToolAdapter):
    """Claude Code 和 claude-internal 的公共逻辑基类。"""

    _dir_name: str  # "claude" 或 "claude-internal"

    # ── 本地发现 ──────────────────────────────────────────────────────────────

    def local_sessions(self) -> list[tuple[Path, str]]:
        sessions: list[tuple[Path, str]] = []
        projects_dir = Path.home() / f".{self._dir_name}" / "projects"
        if not projects_dir.is_dir():
            return []
        for jsonl_file in projects_dir.rglob("*.jsonl"):
            if "subagents" in str(jsonl_file):
                continue
            rel = jsonl_file.relative_to(projects_dir)
            project_name = str(rel.parts[0]) if len(rel.parts) > 1 else "default"
            sessions.append((jsonl_file, project_name))
        return sessions

    # ── 归档 ──────────────────────────────────────────────────────────────────

    def copy_to_archive(self, src: Path, project: str, archive_dir: Path) -> Path:
        dest = archive_dir / "archive" / self.tool_name / project / src.name
        self._copy_file_if_newer(src, dest)
        return dest

    def archive_sessions(self, archive_dir: Path) -> list[tuple[Path, str, str]]:
        return self._jsonl_archive_sessions(archive_dir)

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
        first_ts = None
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
                if not SKIP_FOR_TITLE_RE.match(clean_text):
                    uq_match = USER_QUERY_RE.search(clean_text)
                    first_user_text = (
                        uq_match.group(1).strip()[:200] if uq_match else clean_text[:200]
                    )

            turns.append({"role": msg_type, "text": clean_text})

        if len(turns) < 2:
            return None

        result: dict = {
            "id": path.stem,
            "source": self.tool_name,
            "file": str(path),
            "title": extract_title(first_user_text),
            "first_question": first_user_text,
            "turn_count": len(turns),
            "user_turns": sum(1 for t in turns if t["role"] == "user"),
            "assistant_turns": sum(1 for t in turns if t["role"] == "assistant"),
            "timestamp": first_ts,
            "turns": turns,
        }
        if cwd:
            result["cwd"] = cwd
        return result

    # ── 远程 ──────────────────────────────────────────────────────────────────

    def remote_section_marker(self) -> str:
        # "claude" → "__CLAUDE__" / "claude-internal" → "__CLAUDE_INTERNAL__"
        return f"__{self.tool_name.upper().replace('-', '_')}__"

    def remote_find_cmd(self) -> str:
        return (
            f"find ~/.{self._dir_name}/projects -maxdepth 4 -name '*.jsonl'"
            " ! -path '*/subagents/*' 2>/dev/null | head -200"
        )

    def remote_rsync(self, host: str, archive_dir: Path) -> tuple[str, Path]:
        return (
            f"{host}:~/.{self._dir_name}/projects/",
            archive_dir / "archive" / host / self.tool_name,
        )


class ClaudeAdapter(_ClaudeBaseAdapter):
    tool_name = "claude"
    label = "◆ Claude"
    _dir_name = "claude"


class ClaudeInternalAdapter(_ClaudeBaseAdapter):
    tool_name = "claude-internal"
    label = "◆ claude-internal"
    _dir_name = "claude-internal"
