"""adapters/__init__.py — 导出全局 ADAPTERS 列表和 ADAPTER_BY_NAME 字典。

新增工具时：
1. 在此目录下新建 your_tool.py，继承 ToolAdapter 实现必要方法
2. 在下方 import 并添加到 ADAPTERS 列表
"""
from .claude import ClaudeAdapter, ClaudeInternalAdapter
from .codebuddy import CodeBuddyAdapter
from .codebuddy_ide import CodeBuddyIDEAdapter
from .cursor import CursorAdapter

ADAPTERS = [
    CursorAdapter(),
    ClaudeAdapter(),
    ClaudeInternalAdapter(),
    CodeBuddyAdapter(),
    CodeBuddyIDEAdapter(),
]

ADAPTER_BY_NAME: dict = {a.tool_name: a for a in ADAPTERS}
