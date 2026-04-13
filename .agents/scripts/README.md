# .agents 初始化脚本

将 `.agents/` 下的配置资产（skills、commands、rules 等）链接到各 AI 工具目录。

## 快速开始

```bash
# 初始化所有资产
./.agents/scripts/init.sh

# 或通过 pnpm
pnpm agents:init
```

## 命令行选项

```
用法: init.sh [选项] [资产类型...]
```

| 选项             | 说明                             |
| ---------------- | -------------------------------- |
| `-n, --dry-run`  | 预览变更，不执行实际操作         |
| `-f, --force`    | 强制修复指向错误的链接           |
| `-c, --clean`    | 仅清理悬空链接，不创建新链接     |
| `-u, --unlink`   | 移除所有由 init 创建的符号链接   |
| `-v, --verbose`  | 显示调试信息                     |
| `-q, --quiet`    | 静默模式，仅显示变更和错误       |
| `-h, --help`     | 显示帮助信息                     |

### 示例

```bash
init.sh                    # 初始化所有资产类型
init.sh skills             # 仅初始化 skills
init.sh skills commands    # 初始化 skills 和 commands
init.sh --force            # 修复所有指向错误的链接
init.sh --dry-run          # 预览变更
init.sh --clean            # 清理悬空链接
init.sh --unlink           # 移除所有由 init 创建的符号链接
init.sh --unlink --dry-run # 预览要移除的链接
init.sh --force --dry-run  # 预览修复操作
```

## 工作原理

### 自动发现

脚本自动完成两件事：

1. **检测工具目录** — 扫描项目根目录，识别已存在的 AI 工具目录（`.claude/`, `.cursor/`, `.codebuddy/` 等）
2. **发现资产类型** — 扫描 `.agents/` 下有内容的子目录（排除 `scripts/` 等内部目录）

不再需要手动维护工具列表或资产类型列表，新增资产或工具目录后直接运行 `init.sh` 即可。

### 链接策略

使用 **单项链接**（而非整目录链接），保留用户在各工具目录中的私有配置：

```
.claude/skills/brainstorming     → ../../.agents/skills/brainstorming
.cursor/skills/brainstorming     → ../../.agents/skills/brainstorming
.claude/commands/openspec        → ../../.agents/commands/openspec
```

### 异常处理

| 情况                 | 处理                           |
| -------------------- | ------------------------------ |
| 链接已存在且正确     | 跳过                           |
| 链接指向错误目标     | 警告（`--force` 时自动修复）   |
| 目标已是目录或文件   | 跳过，保留用户配置             |
| 悬空链接（指向已删除资产） | 自动清理                 |
| 工具目录不存在       | 静默跳过                       |
| 工具子目录不存在     | 自动创建                       |

## 配置文件

可通过 `.agents/config` 自定义行为：

```bash
# 指定链接目标（逗号分隔，默认自动检测）
TOOL_DIRS=.claude,.codebuddy,.cursor

# 排除不参与链接的目录（逗号分隔，默认排除 scripts）
EXCLUDE_DIRS=scripts
```

## 脚本文件

| 文件               | 说明                              |
| ------------------ | --------------------------------- |
| `init.sh`          | 主入口，支持所有选项和资产类型参数 |
| `common.sh`        | 共用函数库                        |
| `init-skills.sh`   | 兼容入口，等同 `init.sh skills`   |
| `init-commands.sh` | 兼容入口，等同 `init.sh commands` |

## 添加新资产

1. 在 `.agents/` 下创建目录和内容：

   ```bash
   mkdir -p .agents/skills/my-skill
   echo "# My Skill" > .agents/skills/my-skill/SKILL.md
   ```

2. 运行初始化：

   ```bash
   ./.agents/scripts/init.sh
   ```

脚本会自动发现新资产并链接到所有已检测的工具目录。

## 自动触发

可配置 Git Hooks，在以下场景自动运行初始化：

| 场景                            | 触发 Hook       |
| ------------------------------- | --------------- |
| `pnpm install`                  | `prepare` 脚本  |
| `git checkout` / `git switch`   | `post-checkout` |
| `git pull` / `git merge`        | `post-merge`    |
