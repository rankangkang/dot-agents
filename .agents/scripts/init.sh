#!/bin/bash

# .agents 统一初始化脚本
# 将 .agents/ 下的资产（skills、commands、rules 等）链接到各 AI 工具目录
#
# 使用方法: ./.agents/scripts/init.sh [选项] [资产类型...]
# 详细帮助: ./.agents/scripts/init.sh --help

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENTS_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$AGENTS_DIR")"

show_usage() {
    cat << 'EOF'
用法: init.sh [选项] [资产类型...]

将 .agents/ 下的资产链接到各 AI 工具目录（.claude, .cursor 等）

选项:
  -n, --dry-run        预览变更，不执行实际操作
  -f, --force          强制修复指向错误的链接
  -c, --clean          仅清理悬空链接，不创建新链接
  -g, --global         链接到全局目录（$HOME）而非当前项目
  -t, --target <dir>   链接到指定目录
  -v, --verbose        显示详细调试信息
  -q, --quiet          静默模式，仅显示变更和错误
  -h, --help           显示此帮助信息

示例:
  init.sh                        初始化所有资产类型（链接到当前项目）
  init.sh skills                 仅初始化 skills
  init.sh skills commands        初始化 skills 和 commands
  init.sh --global               链接到全局目录 (~/.cursor/skills/ 等)
  init.sh --global skills        仅将 skills 链接到全局目录
  init.sh --target ~/other-proj  链接到其他项目目录
  init.sh --force                强制修复所有错误链接
  init.sh --dry-run skills       预览 skills 链接变更
  init.sh --clean                清理所有悬空链接
EOF
}

# ── 解析参数 ──

export DRY_RUN=false
export FORCE=false
export VERBOSE=false
export QUIET=false
CLEAN_ONLY=false
GLOBAL=false
TARGET_DIR=""
ASSET_TYPES=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        -n|--dry-run) DRY_RUN=true ;;
        -f|--force)   FORCE=true ;;
        -c|--clean)   CLEAN_ONLY=true ;;
        -g|--global)  GLOBAL=true ;;
        -t|--target)  [[ -z "${2:-}" || "$2" == -* ]] && { echo "--target 需要指定目录"; exit 1; }; TARGET_DIR="$2"; shift ;;
        -v|--verbose) VERBOSE=true ;;
        -q|--quiet)   QUIET=true ;;
        -h|--help)    show_usage; exit 0 ;;
        -*)           echo "未知选项: $1 (使用 --help 查看帮助)"; exit 1 ;;
        *)            ASSET_TYPES+=("$1") ;;
    esac
    shift
done

source "$SCRIPT_DIR/common.sh"

# ── 确定目标根目录 ──

if [[ -n "$TARGET_DIR" ]]; then
    if [[ ! -d "$TARGET_DIR" ]]; then
        echo "目标目录不存在: $TARGET_DIR"; exit 1
    fi
    TARGET_ROOT="$(cd "$TARGET_DIR" && pwd)"
elif $GLOBAL; then
    TARGET_ROOT="$HOME"
else
    TARGET_ROOT="$PROJECT_ROOT"
fi

# ── 加载配置 ──

load_config "$AGENTS_DIR/config"

# ── 检测工具目录 ──

TOOL_DIRS_STR=$(detect_tool_dirs "$TARGET_ROOT")

if [[ -z "$TOOL_DIRS_STR" ]]; then
    log_info "未检测到 AI 工具目录（在 $TARGET_ROOT 中），无需链接"
    exit 0
fi

# ── 确定资产类型 ──

if [[ ${#ASSET_TYPES[@]} -eq 0 ]]; then
    read -ra ASSET_TYPES <<< "$(discover_asset_types "$AGENTS_DIR")"
fi

if [[ ${#ASSET_TYPES[@]} -eq 0 ]]; then
    log_info "未发现需要链接的资产"
    exit 0
fi

# ── 头部 ──

if ! $QUIET; then
    echo ""
    echo "========================================"
    echo "  .agents 初始化"
    $DRY_RUN    && echo "  模式: 预览 (dry-run)"
    $FORCE      && echo "  模式: 强制修复 (force)"
    $CLEAN_ONLY && echo "  模式: 仅清理 (clean)"
    [[ "$TARGET_ROOT" != "$PROJECT_ROOT" ]] && echo "  目标: $TARGET_ROOT"
    echo "  工具: $TOOL_DIRS_STR"
    echo "  资产: ${ASSET_TYPES[*]}"
    echo "========================================"
fi

# ── 执行 ──

if $CLEAN_ONLY; then
    if ! $QUIET; then
        echo ""
        echo -e "${BLUE}── 清理悬空链接 ──${NC}"
    fi

    reset_counts

    read -ra _tool_dirs <<< "$TOOL_DIRS_STR"
    for tool_dir in "${_tool_dirs[@]}"; do
        [[ ! -d "$TARGET_ROOT/$tool_dir" ]] && continue
        for asset_type in "${ASSET_TYPES[@]}"; do
            clean_stale_links "$asset_type" "$tool_dir" "$TARGET_ROOT"
        done
    done

    echo ""
    print_summary
else
    for asset_type in "${ASSET_TYPES[@]}"; do
        init_links "$asset_type" "$TARGET_ROOT" "$AGENTS_DIR" "$TOOL_DIRS_STR"
    done
fi

# ── 尾部 ──

if ! $QUIET; then
    echo ""
    echo "========================================"
    echo "  完成"
    echo "========================================"
fi
