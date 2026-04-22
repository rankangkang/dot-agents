#!/bin/bash

# .agents 脚本共用函数库
# 被其他脚本 source 引用

# ── 颜色 ──

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
DIM='\033[2m'
NC='\033[0m'

# ── 全局选项（由调用脚本 export） ──

DRY_RUN=${DRY_RUN:-false}
FORCE=${FORCE:-false}
VERBOSE=${VERBOSE:-false}
QUIET=${QUIET:-false}

# 不参与链接的内部目录（可被 .agents/config 覆盖）
EXCLUDE_DIRS=("scripts")

# 已知的 AI 工具目录名（用于自动检测）
KNOWN_TOOL_DIRS=(
    ".claude" ".codebuddy" ".cursor" ".windsurf"
    ".aider" ".copilot" ".cline" ".roo"
    ".codex" ".continue" ".augment"
)

# ── 统计计数 ──

COUNT_OK=0
COUNT_SKIP=0
COUNT_WARN=0
COUNT_ERROR=0
COUNT_CLEAN=0
COUNT_FIX=0
COUNT_DRY=0

# ── 日志 ──

log_ok()    { ((COUNT_OK++))    || true; echo -e "${GREEN}[OK]${NC}    $1"; }
log_fix()   { ((COUNT_FIX++))   || true; echo -e "${GREEN}[FIX]${NC}   $1"; }
log_skip()  { ((COUNT_SKIP++))  || true; if ! $QUIET; then echo -e "${CYAN}[SKIP]${NC}  $1"; fi; }
log_warn()  { ((COUNT_WARN++))  || true; echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { ((COUNT_ERROR++)) || true; echo -e "${RED}[ERROR]${NC} $1"; }
log_clean() { ((COUNT_CLEAN++)) || true; echo -e "${YELLOW}[CLEAN]${NC} $1"; }
log_info()  { if ! $QUIET; then echo -e "${BLUE}[INFO]${NC}  $1"; fi; }
log_debug() { if $VERBOSE; then echo -e "${DIM}[DEBUG]${NC} $1"; fi; }
log_dry()   { ((COUNT_DRY++))   || true; echo -e "${DIM}[DRY]${NC}   $1"; }

print_summary() {
    local parts=()
    ((COUNT_OK    > 0)) && parts+=("${GREEN}${COUNT_OK} 创建${NC}")
    ((COUNT_FIX   > 0)) && parts+=("${GREEN}${COUNT_FIX} 修复${NC}")
    ((COUNT_CLEAN > 0)) && parts+=("${YELLOW}${COUNT_CLEAN} 清理${NC}")
    ((COUNT_DRY   > 0)) && parts+=("${DIM}${COUNT_DRY} 预览${NC}")
    ((COUNT_SKIP  > 0)) && parts+=("${CYAN}${COUNT_SKIP} 跳过${NC}")
    ((COUNT_WARN  > 0)) && parts+=("${YELLOW}${COUNT_WARN} 警告${NC}")
    ((COUNT_ERROR > 0)) && parts+=("${RED}${COUNT_ERROR} 错误${NC}")

    if [[ ${#parts[@]} -eq 0 ]]; then
        echo -e "  ${DIM}无变更${NC}"
        return
    fi

    local result="${parts[0]}"
    for ((i = 1; i < ${#parts[@]}; i++)); do
        result+=", ${parts[$i]}"
    done
    echo -e "  结果: $result"
}

reset_counts() {
    COUNT_OK=0; COUNT_SKIP=0; COUNT_WARN=0
    COUNT_ERROR=0; COUNT_CLEAN=0; COUNT_FIX=0; COUNT_DRY=0
}

# ── 配置加载 ──

load_config() {
    local config_file="$1"
    [[ ! -f "$config_file" ]] && return 0

    log_debug "加载配置: $config_file"

    local val
    val=$(grep -E '^TOOL_DIRS=' "$config_file" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d "\"' ")
    [[ -n "$val" ]] && CONFIG_TOOL_DIRS="${val//,/ }"

    val=$(grep -E '^EXCLUDE_DIRS=' "$config_file" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d "\"' ")
    if [[ -n "$val" ]]; then
        IFS=',' read -ra EXCLUDE_DIRS <<< "$val"
    fi
}

# ── 工具目录检测 ──
# 优先使用配置文件，否则自动检测项目中已存在的 AI 工具目录

detect_tool_dirs() {
    local project_root="$1"

    if [[ -n "${CONFIG_TOOL_DIRS:-}" ]]; then
        log_debug "使用配置的 TOOL_DIRS: $CONFIG_TOOL_DIRS"
        echo "$CONFIG_TOOL_DIRS"
        return 0
    fi

    local detected=()
    for pattern in "${KNOWN_TOOL_DIRS[@]}"; do
        [[ -d "$project_root/$pattern" ]] && detected+=("$pattern")
    done

    if [[ ${#detected[@]} -gt 0 ]]; then
        log_debug "自动检测到: ${detected[*]}"
        echo "${detected[*]}"
    fi
}

# ── 资产类型自动发现 ──
# 扫描 .agents/ 下有实际内容的子目录（排除内部目录）

discover_asset_types() {
    local agents_dir="$1"
    local types=()

    for dir in "$agents_dir"/*/; do
        [[ ! -d "$dir" ]] && continue
        local name
        name=$(basename "$dir")

        local excluded=false
        for ex in "${EXCLUDE_DIRS[@]}"; do
            [[ "$name" == "$ex" ]] && { excluded=true; break; }
        done
        $excluded && continue

        local has_content=false
        for subdir in "$dir"*/; do
            [[ -d "$subdir" ]] && { has_content=true; break; }
        done
        if ! $has_content; then
            for file in "$dir"*; do
                [[ -f "$file" ]] && [[ "$(basename "$file")" != .* ]] && { has_content=true; break; }
            done
        fi
        $has_content && types+=("$name")
    done

    echo "${types[*]}"
}

# ── 相对路径计算（兼容 macOS / Linux） ──

get_relative_path() {
    local source="$1"
    local target_dir="$2"

    if command -v python3 &>/dev/null; then
        python3 -c 'import os,sys; print(os.path.relpath(sys.argv[1], sys.argv[2]))' \
            "$source" "$target_dir"
        return 0
    fi

    if realpath --relative-to="$target_dir" "$source" 2>/dev/null; then
        return 0
    fi

    if command -v node &>/dev/null; then
        node -e 'console.log(require("path").relative(process.argv[1], process.argv[2]))' \
            "$target_dir" "$source"
        return 0
    fi

    _relpath_fallback "$source" "$target_dir"
}

resolve_link_path_lexically() {
    local base_dir="$1"
    local link_target="$2"

    if command -v python3 &>/dev/null; then
        python3 -c 'import os,sys; base=sys.argv[1]; target=sys.argv[2]; print(os.path.normpath(target if os.path.isabs(target) else os.path.join(base, target)))' \
            "$base_dir" "$link_target"
        return 0
    fi

    if command -v node &>/dev/null; then
        node -e 'const path=require("path"); const base=process.argv[1]; const target=process.argv[2]; console.log(path.normalize(path.isAbsolute(target) ? target : path.join(base, target)))' \
            "$base_dir" "$link_target"
        return 0
    fi

    _resolve_link_path_fallback "$base_dir" "$link_target"
}

_resolve_link_path_fallback() {
    local base_dir="$1"
    local link_target="$2"
    local combined

    if [[ "$link_target" == /* ]]; then
        combined="$link_target"
    else
        combined="$base_dir/$link_target"
    fi

    local absolute=false
    [[ "$combined" == /* ]] && absolute=true

    local IFS='/'
    local -a parts=()
    local -a stack=()
    read -r -a parts <<< "$combined"

    local part
    for part in "${parts[@]}"; do
        [[ -z "$part" || "$part" == "." ]] && continue

        if [[ "$part" == ".." ]]; then
            if [[ ${#stack[@]} -gt 0 && "${stack[${#stack[@]}-1]}" != ".." ]]; then
                unset "stack[${#stack[@]}-1]"
            elif ! $absolute; then
                stack+=("$part")
            fi
            continue
        fi

        stack+=("$part")
    done

    local result=""
    if $absolute; then
        result="/"
    fi

    local idx
    for idx in "${!stack[@]}"; do
        if [[ -n "$result" && "$result" != "/" ]]; then
            result+="/"
        fi
        result+="${stack[$idx]}"
    done

    if [[ -z "$result" ]]; then
        $absolute && echo "/" || echo "."
        return 0
    fi

    echo "$result"
}

_relpath_fallback() {
    local source="$1"
    local target="$2"

    [[ "$source" != /* ]] && source="$(pwd)/$source"
    [[ "$target" != /* ]] && target="$(pwd)/$target"
    source="${source%/}"
    target="${target%/}"

    local common="$target"
    local up=""

    while [[ "$source" != "$common"/* && "$source" != "$common" ]]; do
        common="$(dirname "$common")"
        up="../$up"
    done

    if [[ "$source" == "$common" ]]; then
        echo "."
    else
        echo "${up}${source#"$common"/}"
    fi
}

# ── 链接创建 ──

create_link() {
    local item_type="$1"
    local item_name="$2"
    local tool_dir="$3"
    local project_root="$4"
    local agents_dir="$5"

    local source_path="$agents_dir/$item_type/$item_name"
    local target_dir="$project_root/$tool_dir/$item_type"
    local target_path="$target_dir/$item_name"
    local display="$tool_dir/$item_type/$item_name"

    if [[ -L "$source_path" ]]; then
        log_warn "$item_name: 源是链接，跳过"
        return 0
    fi

    [[ ! -d "$project_root/$tool_dir" ]] && return 0

    # 目标已存在 — 处理各种情况
    if [[ -e "$target_path" || -L "$target_path" ]]; then
        if [[ -L "$target_path" ]]; then
            local link_target current
            link_target=$(get_relative_path "$source_path" "$target_dir")
            current=$(readlink "$target_path")

            if [[ "$current" == "$link_target" ]]; then
                log_skip "$display"
                return 0
            fi

            if $FORCE; then
                if $DRY_RUN; then
                    log_dry "修复 $display ($current -> $link_target)"
                else
                    rm "$target_path"
                    ln -s "$link_target" "$target_path"
                    log_fix "$display ($current -> $link_target)"
                fi
            else
                log_warn "$display 指向 $current (用 --force 修复)"
            fi
            return 0
        fi

        if [[ -d "$target_path" ]]; then
            log_skip "$display (目录已存在)"
            return 0
        fi

        if [[ -f "$target_path" ]]; then
            log_warn "$display 是普通文件，跳过"
            return 0
        fi
    fi

    # 确保目标目录存在
    if [[ ! -d "$target_dir" ]]; then
        if $DRY_RUN; then
            log_dry "创建目录 $tool_dir/$item_type/"
        else
            mkdir -p "$target_dir"
            log_debug "创建目录 $tool_dir/$item_type/"
        fi
    fi

    local link_target
    link_target=$(get_relative_path "$source_path" "$target_dir")
    log_debug "$display -> $link_target"

    if $DRY_RUN; then
        log_dry "创建 $display"
    elif ln -s "$link_target" "$target_path" 2>/dev/null; then
        log_ok "$display"
    else
        log_error "创建失败 $display"
    fi
}

# ── 悬空链接清理 ──

clean_stale_links() {
    local item_type="$1"
    local tool_dir="$2"
    local project_root="$3"

    local target_dir="$project_root/$tool_dir/$item_type"
    [[ ! -d "$target_dir" ]] && return 0

    for entry in "$target_dir"/*; do
        [[ "$entry" == "$target_dir/*" ]] && break
        [[ ! -L "$entry" ]] && continue
        [[ -e "$entry" ]] && continue

        local display="$tool_dir/$item_type/$(basename "$entry")"
        if $DRY_RUN; then
            log_dry "清理 $display"
        else
            rm "$entry"
            log_clean "$display"
        fi
    done
}

# ── 清理所有由 init 创建的链接 ──

purge_links() {
    local item_type="$1"
    local tool_dir="$2"
    local project_root="$3"
    local agents_dir="$4"

    local target_dir="$project_root/$tool_dir/$item_type"
    [[ ! -d "$target_dir" ]] && return 0

    local agents_real
    agents_real="$(cd "$agents_dir" && pwd -P)"

    for entry in "$target_dir"/*; do
        [[ "$entry" == "$target_dir/*" ]] && break
        [[ ! -L "$entry" ]] && continue

        local raw_target
        raw_target=$(readlink "$entry") || continue

        local link_dest
        link_dest=$(resolve_link_path_lexically "$target_dir" "$raw_target") || continue

        case "$link_dest" in
            "$agents_real"|\
            "$agents_real"/*)
                local display="$tool_dir/$item_type/$(basename "$entry")"
                if $DRY_RUN; then
                    log_dry "移除 $display"
                else
                    rm "$entry"
                    log_clean "$display"
                fi
                ;;
        esac
    done

    if [[ -d "$target_dir" ]] && ! $DRY_RUN; then
        local remaining
        remaining=$(ls -A "$target_dir" 2>/dev/null)
        if [[ -z "$remaining" ]]; then
            rmdir "$target_dir" 2>/dev/null && log_debug "移除空目录 $tool_dir/$item_type/"
        fi
    fi
}

# ── 初始化链接（主逻辑） ──

init_links() {
    local item_type="$1"
    local project_root="$2"
    local agents_dir="$3"
    local tool_dirs_str="$4"
    local source_dir="$agents_dir/$item_type"

    local display_name
    display_name="$(tr '[:lower:]' '[:upper:]' <<< "${item_type:0:1}")${item_type:1}"

    echo ""
    if ! $QUIET; then
        echo -e "${BLUE}── $display_name ──${NC}"
    fi

    reset_counts

    if [[ ! -d "$source_dir" ]]; then
        log_info ".agents/$item_type/ 不存在，跳过"
        return 0
    fi

    local items=()
    for item_path in "$source_dir"/*/; do
        [[ ! -d "$item_path" ]] && continue
        items+=("$(basename "$item_path")")
    done
    for item_path in "$source_dir"/*; do
        [[ ! -f "$item_path" ]] && continue
        local fname
        fname=$(basename "$item_path")
        [[ "$fname" == .* ]] && continue
        items+=("$fname")
    done

    if [[ ${#items[@]} -eq 0 ]]; then
        log_info ".agents/$item_type/ 为空，跳过"
        return 0
    fi

    log_info "发现 ${#items[@]} 个 $display_name: ${items[*]}"

    local tool_dirs
    read -ra tool_dirs <<< "$tool_dirs_str"

    for tool_dir in "${tool_dirs[@]}"; do
        [[ ! -d "$project_root/$tool_dir" ]] && continue
        log_debug "处理 $tool_dir..."

        for item_name in "${items[@]}"; do
            create_link "$item_type" "$item_name" "$tool_dir" "$project_root" "$agents_dir"
        done

        clean_stale_links "$item_type" "$tool_dir" "$project_root"
    done

    echo ""
    print_summary

    [[ $COUNT_ERROR -eq 0 ]]
}
