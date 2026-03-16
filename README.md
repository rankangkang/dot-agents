# agent-spec

AI 资产管理仓库 — 统一存放和管理 Agent 相关的技能（Skills）、规则（Rules）、脚本（Scripts）、命令（Commands）等配置资产，并通过符号链接分发到各 AI 工具目录。

## 快速开始

```bash
# 链接资产到当前项目内的 AI 工具目录（.cursor、.claude 等）
.agents/scripts/init.sh

# 链接资产到全局目录（~/.cursor/skills/ 等）
.agents/scripts/init.sh --global

# 先预览，不实际执行
.agents/scripts/init.sh --global --dry-run
```

所有 AI 资产统一存放在 `.agents/` 目录下，详见 [.agents/README.md](.agents/README.md)。

## 目录结构

```
.
├── .agents/
│   ├── skills/      # Agent 技能定义
│   ├── rules/       # Agent 行为规则
│   ├── scripts/     # 初始化与自动化脚本
│   ├── commands/    # 自定义命令
│   ├── prompts/     # Prompt 模板
│   ├── templates/   # 项目/文件模板
│   └── config       # 工具目录与排除目录配置
└── README.md
```

## 初始化脚本

`init.sh` 将 `.agents/` 下的资产通过符号链接分发到 AI 工具目录（如 `.cursor/skills/`、`.claude/commands/`）。

```bash
init.sh [选项] [资产类型...]
```

| 选项 | 说明 |
|---|---|
| `-g, --global` | 链接到全局目录（`$HOME`）而非当前项目 |
| `-t, --target <dir>` | 链接到指定目录 |
| `-n, --dry-run` | 预览变更，不实际执行 |
| `-f, --force` | 强制修复指向错误的链接 |
| `-c, --clean` | 仅清理悬空链接 |
| `-v, --verbose` | 显示详细调试信息 |
| `-q, --quiet` | 静默模式 |

**示例：**

```bash
# 仅链接 skills
init.sh skills

# 将 skills 链接到全局 ~/.cursor/skills/ 等
init.sh --global skills

# 链接到另一个项目
init.sh --target ~/other-project

# 强制修复所有错误链接
init.sh --force
```
