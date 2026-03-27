"""adapters/codebuddy_ide.py — CodeBuddy IDE（目录结构格式）适配器。

目录布局（本地）:
  macOS: ~/Library/Application Support/CodeBuddyExtension/Data/.../history/{workspaceHash}/{convId}/
  Linux: ~/.local/share/CodeBuddyExtension/Data/{userId}/CodeBuddyIDE/{userId}/history/{workspaceHash}/{convId}/

会话目录内容:
  index.json        — 消息列表（有序） + requests（含时间戳）
  messages/
    {msgId}.json    — 单条消息文件
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .base import (
    ToolAdapter,
    SKIP_FOR_TITLE_RE,
    USER_QUERY_RE,
    extract_title,
    strip_noise,
)


class CodeBuddyIDEAdapter(ToolAdapter):
    """CodeBuddy IDE（目录结构格式）适配器。支持 macOS 和 Linux。"""

    tool_name = "codebuddy-ide"
    label = "★ CodeBuddy IDE"

    # ── 路径发现 ──────────────────────────────────────────────────────────────

    def _find_history_dirs(self) -> list[Path]:
        """发现本机所有 history 目录，兼容 macOS 和 Linux 路径结构。"""
        dirs: list[Path] = []
        found = set()

        def _add(p: Path):
            if p.is_dir() and p not in found:
                found.add(p)
                dirs.append(p)

        # macOS: ~/Library/Application Support/CodeBuddyExtension/Data/
        # history 可能直接在 Data/ 下或嵌套 1-2 层
        macos_base = (
            Path.home() / "Library" / "Application Support"
            / "CodeBuddyExtension" / "Data"
        )
        if macos_base.is_dir():
            for pattern in ["history", "*/history", "*/*/history"]:
                for hist in macos_base.glob(pattern):
                    _add(hist)

        # Linux: ~/.local/share/CodeBuddyExtension/Data/{userId}/CodeBuddyIDE/{userId}/history/
        # userId 是 UUID，用 glob 通配
        linux_base = Path.home() / ".local" / "share" / "CodeBuddyExtension"
        if linux_base.is_dir():
            for hist in linux_base.glob("Data/*/CodeBuddyIDE/*/history"):
                _add(hist)

        return dirs

    # ── 本地发现 ──────────────────────────────────────────────────────────────

    def local_sessions(self) -> list[tuple[Path, str]]:
        sessions: list[tuple[Path, str]] = []
        for hist_dir in self._find_history_dirs():
            for workspace_dir in hist_dir.iterdir():
                if not workspace_dir.is_dir():
                    continue
                for conv_dir in workspace_dir.iterdir():
                    if not conv_dir.is_dir():
                        continue
                    if (conv_dir / "index.json").exists():
                        sessions.append((conv_dir, workspace_dir.name))
        return sessions

    # ── 归档 ──────────────────────────────────────────────────────────────────

    def copy_to_archive(self, src: Path, project: str, archive_dir: Path) -> Path:
        dest = archive_dir / "archive" / "codebuddy-ide" / project / src.name
        self._copy_dir_if_newer(src, dest)
        return dest

    def archive_sessions(self, archive_dir: Path) -> list[tuple[Path, str, str]]:
        sessions: list[tuple[Path, str, str]] = []
        cb_archive = archive_dir / "archive" / "codebuddy-ide"
        if not cb_archive.is_dir():
            return []
        for workspace_dir in cb_archive.iterdir():
            if not workspace_dir.is_dir():
                continue
            for conv_dir in workspace_dir.iterdir():
                if not conv_dir.is_dir():
                    continue
                if (conv_dir / "index.json").exists():
                    sessions.append((conv_dir, workspace_dir.name, "localhost"))
        return sessions

    # ── 指纹（目录哈希）──────────────────────────────────────────────────────

    def fingerprint(self, path: Path) -> str:
        parts: list[str] = []
        try:
            for f in sorted(path.rglob("*")):
                if f.is_file():
                    st = f.stat()
                    parts.append(f"{f.name}:{st.st_mtime:.6f}:{st.st_size}")
        except Exception:
            pass
        return hashlib.md5("|".join(parts).encode()).hexdigest()[:12] if parts else ""

    # ── 解析 ──────────────────────────────────────────────────────────────────

    def parse(self, path: Path) -> dict | None:
        index_path = path / "index.json"
        if not index_path.exists():
            return None

        try:
            index = json.loads(index_path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            return None

        msg_list = index.get("messages", [])
        if not msg_list:
            return None

        # 从 requests[0].startedAt 提取会话时间戳
        first_ts = None
        requests = index.get("requests", [])
        if requests:
            try:
                started = requests[0].get("startedAt")
                if isinstance(started, (int, float)):
                    first_ts = datetime.fromtimestamp(
                        started / 1000, tz=timezone.utc
                    ).isoformat()
            except Exception:
                pass

        # 加载 messages/ 目录下的消息文件
        msg_files: dict[str, Path] = {}
        msgs_dir = path / "messages"
        if msgs_dir.is_dir():
            for f in msgs_dir.iterdir():
                if f.suffix == ".json":
                    msg_files[f.stem] = f

        turns: list[dict] = []
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

            text_parts = [
                block.get("text", "")
                for block in content_blocks
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            full_text = "\n".join(text_parts).strip()
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

        return {
            "id": path.name,
            "source": "codebuddy-ide",
            "file": str(path),
            "title": extract_title(first_user_text),
            "first_question": first_user_text,
            "turn_count": len(turns),
            "user_turns": sum(1 for t in turns if t["role"] == "user"),
            "assistant_turns": sum(1 for t in turns if t["role"] == "assistant"),
            "timestamp": first_ts,
            "turns": turns,
        }

    # CodeBuddy IDE 暂不支持远程 SSH 扫描和 rsync（remote_* 返回默认 None）
