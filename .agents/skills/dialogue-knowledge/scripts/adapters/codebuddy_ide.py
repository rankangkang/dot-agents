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
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .base import (
    KNOWN_TOOL_DIRS,
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

    def _sessions_under_cb_root(self, cb_root: Path, host: str) -> list[tuple[Path, str, str]]:
        sessions: list[tuple[Path, str, str]] = []
        if not cb_root.is_dir():
            return sessions
        for workspace_dir in cb_root.iterdir():
            if not workspace_dir.is_dir():
                continue
            for conv_dir in workspace_dir.iterdir():
                if not conv_dir.is_dir():
                    continue
                if (conv_dir / "index.json").exists():
                    sessions.append((conv_dir, workspace_dir.name, host))
        return sessions

    def archive_sessions(self, archive_dir: Path) -> list[tuple[Path, str, str]]:
        out: list[tuple[Path, str, str]] = []
        out.extend(
            self._sessions_under_cb_root(
                archive_dir / "archive" / "codebuddy-ide", "localhost"
            )
        )
        archive = archive_dir / "archive"
        if archive.is_dir():
            for host_dir in sorted(archive.iterdir()):
                if not host_dir.is_dir() or host_dir.name in KNOWN_TOOL_DIRS:
                    continue
                tool_dir = host_dir / "codebuddy-ide"
                out.extend(self._sessions_under_cb_root(tool_dir, host_dir.name))
        return out

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

    # ── 远程（SSH / rsync 目录树）────────────────────────────────────────────

    def remote_section_marker(self) -> str:
        return "__CODEBUDDY_IDE__"

    def remote_find_cmd(self) -> str:
        # Linux: .../CodeBuddyIDE/.../history/{workspace}/{conv}/index.json
        # macOS: .../Data/.../history/{workspace}/{conv}/index.json
        return (
            "("
            "find \"$HOME/.local/share/CodeBuddyExtension/Data\" "
            "-path '*/CodeBuddyIDE/*/history/*/*/index.json' 2>/dev/null; "
            "find \"$HOME/Library/Application Support/CodeBuddyExtension/Data\" "
            "-path '*/history/*/*/index.json' 2>/dev/null"
            ") | head -200"
        )

    def _remote_history_roots_shell(self) -> str:
        """在远程 shell 中输出各 history 根目录（每行一个绝对路径）。"""
        return (
            r'for d in "$HOME"/.local/share/CodeBuddyExtension/Data/*/CodeBuddyIDE/*/history; do '
            r'[ -d "$d" ] && printf "%s\n" "$d"; done; '
            r'if [ -d "$HOME/Library/Application Support/CodeBuddyExtension/Data" ]; then '
            r'find "$HOME/Library/Application Support/CodeBuddyExtension/Data" -type d '
            r'-name history 2>/dev/null; fi'
        )

    @staticmethod
    def _count_rsync_transferred_files(stdout: str) -> int:
        return sum(
            1
            for line in stdout.splitlines()
            if line.strip().endswith(".json")
        )

    def remote_sync(self, host: str, archive_dir: Path, timeout: int = 180) -> list[dict] | None:
        """将远程 history 目录树 rsync 到 archive/{host}/codebuddy-ide/。"""
        local_dest = archive_dir / "archive" / host / "codebuddy-ide"
        local_dest.mkdir(parents=True, exist_ok=True)

        list_cmd = self._remote_history_roots_shell()
        try:
            proc = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes", host, list_cmd],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            return [{
                "host": host,
                "tool": self.tool_name,
                "status": "error",
                "files_synced": 0,
                "message": str(e)[:200],
            }]

        roots = sorted({ln.strip() for ln in proc.stdout.splitlines() if ln.strip()})
        if not roots and proc.returncode != 0:
            return [{
                "host": host,
                "tool": self.tool_name,
                "status": "error",
                "files_synced": 0,
                "message": (proc.stderr or proc.stdout or "")[:200],
            }]
        if not roots:
            return [{
                "host": host,
                "tool": self.tool_name,
                "status": "success",
                "files_synced": 0,
                "message": "",
            }]

        per = max(30, timeout // max(1, len(roots)))
        total_files = 0
        last_err = ""
        for root in roots:
            remote_spec = f"{host}:{shlex.quote(root.rstrip('/')) + '/'}"
            try:
                rp = subprocess.run(
                    [
                        "rsync",
                        "-avz",
                        remote_spec,
                        str(local_dest) + "/",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=per,
                )
            except (subprocess.TimeoutExpired, OSError) as e:
                last_err = str(e)[:200]
                break
            if rp.returncode != 0:
                last_err = (rp.stderr or rp.stdout or "")[:200]
                break
            total_files += self._count_rsync_transferred_files(rp.stdout)

        return [{
            "host": host,
            "tool": self.tool_name,
            "status": "success" if not last_err else "error",
            "files_synced": total_files,
            "message": last_err,
        }]
