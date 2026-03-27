"""adapters/base.py — ToolAdapter 抽象基类 + 所有解析器共用的工具函数。"""
from __future__ import annotations

import re
import shutil
from abc import ABC, abstractmethod
from pathlib import Path

# ── 共用噪声模式 ────────────────────────────────────────────────────────────

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

SKIP_FOR_TITLE_RE = re.compile(
    r"^(<local-command|<command-|Caveat: The messages below|<system_reminder>)",
    re.I,
)

USER_QUERY_RE = re.compile(r"<user_query>([\s\S]*?)</user_query>")

# 归档中已知的工具名目录，用于在 archive/ 下区分远程主机目录
KNOWN_TOOL_DIRS = frozenset(
    {"cursor", "claude", "claude-internal", "codebuddy", "codebuddy-ide"}
)


def strip_noise(text: str) -> str:
    """剔除对话内容中的噪声块（thinking/tool_call/system info 等）。"""
    for pattern, replacement in NOISE_PATTERNS:
        text = pattern.sub(replacement, text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_title(text: str) -> str:
    """从用户第一条消息中提取简短标题。"""
    if not text:
        return "Untitled"
    clean = text.strip().split("\n")[0]
    clean = re.sub(r"[#*`@]", "", clean).strip()
    if len(clean) > 80:
        clean = clean[:77] + "..."
    return clean or "Untitled"


# ── ToolAdapter 抽象基类 ─────────────────────────────────────────────────────


class ToolAdapter(ABC):
    """封装单个 AI 工具的对话发现、归档和解析逻辑。

    新增工具时继承此类，实现标注 @abstractmethod 的方法即可。
    """

    tool_name: str = ""  # 子类必须覆盖；工具标识，如 "cursor"
    label: str = ""      # 子类必须覆盖；显示标签，如 "▶ Cursor"（颜色由调用方施加）

    # ── 本地发现 ──────────────────────────────────────────────────────────────

    @abstractmethod
    def local_sessions(self) -> list[tuple[Path, str]]:
        """发现本机所有对话文件/目录。
        返回 [(conversation_path, project_name)] 列表。
        """

    # ── 归档 ──────────────────────────────────────────────────────────────────

    @abstractmethod
    def copy_to_archive(self, src: Path, project: str, archive_dir: Path) -> Path:
        """将对话复制到归档目录，返回目标路径。"""

    @abstractmethod
    def archive_sessions(self, archive_dir: Path) -> list[tuple[Path, str, str]]:
        """枚举归档中属于本工具的所有对话。
        返回 [(path, project, host)] 列表。
        """

    # ── 解析 ──────────────────────────────────────────────────────────────────

    @abstractmethod
    def parse(self, path: Path) -> dict | None:
        """将对话解析为统一结构，无法解析时返回 None。"""

    # ── 指纹（变更检测）──────────────────────────────────────────────────────

    def fingerprint(self, path: Path) -> str:
        """文件指纹（mtime + size）。目录类型可覆盖此方法。"""
        try:
            st = path.stat()
            return f"{st.st_mtime:.6f}:{st.st_size}"
        except Exception:
            return ""

    # ── 远程（SSH / rsync）───────────────────────────────────────────────────

    def remote_section_marker(self) -> str | None:
        """在合并 SSH 命令输出中使用的分节标记（如 "__CURSOR__"）。
        返回 None 表示不支持远程扫描。

        注意：实现此方法时必须同时实现 remote_find_cmd()，两者成对使用。
        """
        return None

    def remote_find_cmd(self) -> str:
        """在远程主机上枚举对话文件的 find 命令片段。
        仅在 remote_section_marker() 非 None 时会被调用。
        """
        return ""

    def remote_rsync(self, host: str, archive_dir: Path) -> tuple[str, Path] | None:
        """返回 (remote_src_url, local_dest_dir) 供 rsync 使用，或 None。
        remote_src_url 格式: "hostname:~/path/to/projects/"
        """
        return None

    # ── 内部辅助 ──────────────────────────────────────────────────────────────

    def _copy_file_if_newer(self, src: Path, dest: Path):
        if dest.exists() and dest.stat().st_mtime >= src.stat().st_mtime:
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    def _copy_dir_if_newer(self, src_dir: Path, dest_dir: Path):
        for src_file in src_dir.rglob("*"):
            if not src_file.is_file():
                continue
            rel = src_file.relative_to(src_dir)
            dest_file = dest_dir / rel
            if dest_file.exists() and dest_file.stat().st_mtime >= src_file.stat().st_mtime:
                continue
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dest_file)

    def _jsonl_archive_sessions(
        self, archive_dir: Path
    ) -> list[tuple[Path, str, str]]:
        """JSONL 类工具的归档枚举辅助方法。

        处理两种布局：
          本机:  archive/{tool_name}/{project}/{id}.jsonl
          远程:  archive/{hostname}/{tool_name}/{project}/{id}.jsonl
        """
        archive = archive_dir / "archive"
        sessions: list[tuple[Path, str, str]] = []

        # 本机路径
        local = archive / self.tool_name
        if local.is_dir():
            for project_dir in sorted(local.iterdir()):
                if not project_dir.is_dir():
                    continue
                for f in sorted(project_dir.glob("*.jsonl")):
                    if "subagents" not in str(f):
                        sessions.append((f, project_dir.name, "localhost"))

        # 远程主机路径：archive/{host}/{tool_name}/...
        if archive.is_dir():
            for host_dir in sorted(archive.iterdir()):
                if not host_dir.is_dir():
                    continue
                if host_dir.name in KNOWN_TOOL_DIRS:
                    continue
                tool_dir = host_dir / self.tool_name
                if not tool_dir.is_dir():
                    continue
                for project_dir in sorted(tool_dir.iterdir()):
                    if not project_dir.is_dir():
                        continue
                    for f in sorted(project_dir.glob("*.jsonl")):
                        if "subagents" not in str(f):
                            sessions.append((f, project_dir.name, host_dir.name))

        return sessions
