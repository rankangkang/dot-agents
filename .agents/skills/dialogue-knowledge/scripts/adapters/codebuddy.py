"""adapters/codebuddy.py — CodeBuddy 插件版适配器（JSONL 格式）。

格式: projects/**/*.jsonl
每行: {type: "message", role: "user"|"assistant",
       content: [{type: "input_text"|"output_text"|"text", text: "..."}]}
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


class CodeBuddyAdapter(ToolAdapter):
    """CodeBuddy 插件（JSONL 格式）适配器。"""

    tool_name = "codebuddy"
    label = "★ CodeBuddy"

    # ── 本地发现 ──────────────────────────────────────────────────────────────

    def local_sessions(self) -> list[tuple[Path, str]]:
        sessions: list[tuple[Path, str]] = []
        projects_dir = Path.home() / ".codebuddy" / "projects"
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
        dest = archive_dir / "archive" / "codebuddy" / project / src.name
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
                if not SKIP_FOR_TITLE_RE.match(clean_text):
                    uq_match = USER_QUERY_RE.search(clean_text)
                    first_user_text = (
                        uq_match.group(1).strip()[:200] if uq_match else clean_text[:200]
                    )

            turns.append({"role": role, "text": clean_text})

        if len(turns) < 2:
            return None

        result: dict = {
            "id": path.stem,
            "source": "codebuddy",
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
        return "__CODEBUDDY__"

    def remote_find_cmd(self) -> str:
        return (
            "find ~/.codebuddy/projects -maxdepth 4 -name '*.jsonl'"
            " ! -path '*/subagents/*' 2>/dev/null | head -200"
        )

    def remote_rsync(self, host: str, archive_dir: Path) -> tuple[str, Path]:
        return (
            f"{host}:~/.codebuddy/projects/",
            archive_dir / "archive" / host / "codebuddy",
        )
