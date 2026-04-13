#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  resolve-review-scope.sh [--mode workspace]
  resolve-review-scope.sh --mode branch [--base <branch>]
  resolve-review-scope.sh --mode range --from <ref> --to <ref>

Options:
  --mode   Review mode: workspace | branch | range
  --base   Base branch/ref for branch mode
  --from   Start ref for range mode
  --to     End ref for range mode
  --help   Show this help message
EOF
}

ensure_git_repo() {
  git rev-parse --show-toplevel >/dev/null 2>&1 || {
    echo "Error: current directory is not inside a git repository." >&2
    exit 1
  }
}

has_head() {
  git rev-parse --verify HEAD >/dev/null 2>&1
}

ref_exists() {
  git rev-parse --verify "${1}^{commit}" >/dev/null 2>&1
}

resolve_default_base() {
  local candidate
  for candidate in origin/main origin/master main master; do
    if ref_exists "$candidate"; then
      echo "$candidate"
      return 0
    fi
  done

  echo "Error: could not detect a default base branch. Tried origin/main, origin/master, main, master." >&2
  exit 1
}

count_files() {
  local data="$1"
  awk 'NF >= 3 { count++ } END { print count + 0 }' <<<"$data"
}

sum_insertions() {
  local data="$1"
  awk 'NF >= 3 && $1 ~ /^[0-9]+$/ { sum += $1 } END { print sum + 0 }' <<<"$data"
}

sum_deletions() {
  local data="$1"
  awk 'NF >= 3 && $2 ~ /^[0-9]+$/ { sum += $2 } END { print sum + 0 }' <<<"$data"
}

print_list() {
  local items="$1"
  local empty_label="$2"

  if [[ -n "$items" ]]; then
    while IFS= read -r line; do
      [[ -n "$line" ]] && printf -- "- %s\n" "$line"
    done <<<"$items"
  else
    printf -- "- %s\n" "$empty_label"
  fi
}

mode="workspace"
base_ref=""
from_ref=""
to_ref=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      [[ $# -ge 2 ]] || { echo "Error: --mode requires a value." >&2; exit 1; }
      mode="$2"
      shift 2
      ;;
    --base)
      [[ $# -ge 2 ]] || { echo "Error: --base requires a value." >&2; exit 1; }
      base_ref="$2"
      shift 2
      ;;
    --from)
      [[ $# -ge 2 ]] || { echo "Error: --from requires a value." >&2; exit 1; }
      from_ref="$2"
      shift 2
      ;;
    --to)
      [[ $# -ge 2 ]] || { echo "Error: --to requires a value." >&2; exit 1; }
      to_ref="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Error: unknown argument '$1'." >&2
      usage >&2
      exit 1
      ;;
  esac
done

case "$mode" in
  workspace|branch|range)
    ;;
  *)
    echo "Error: unsupported mode '$mode'. Expected workspace, branch, or range." >&2
    exit 1
    ;;
esac

ensure_git_repo

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

tmp_diff="$(mktemp)"
trap 'rm -f "$tmp_diff"' EXIT

summary_base=""
summary_head=""
summary_merge_base=""
status="ready"
numstat_data=""
notes=""
untracked_items=""
empty_tree="$(git hash-object -t tree /dev/null)"

case "$mode" in
  workspace)
    summary_head="workspace"
    untracked_items="$(git ls-files --others --exclude-standard)"

    if has_head; then
      summary_base="HEAD"
      git diff HEAD -- >"$tmp_diff"
      numstat_data="$(git diff --numstat HEAD -- || true)"
    else
      summary_base="EMPTY_TREE"
      {
        git diff --cached "$empty_tree" -- || true
        git diff -- || true
      } >"$tmp_diff"
      numstat_data="$(
        {
          git diff --numstat --cached "$empty_tree" -- || true
          git diff --numstat -- || true
        }
      )"
    fi

    notes="reviewing staged + unstaged tracked changes"
    if [[ -n "$untracked_items" ]]; then
      notes="${notes}"$'\n'"untracked files are excluded from the main diff by default"
    fi
    ;;
  branch)
    [[ -n "$base_ref" ]] || base_ref="$(resolve_default_base)"
    ref_exists "$base_ref" || {
      echo "Error: base ref '$base_ref' does not exist." >&2
      exit 1
    }
    has_head || {
      echo "Error: branch mode requires a valid HEAD commit." >&2
      exit 1
    }

    summary_base="$base_ref"
    summary_head="HEAD"
    summary_merge_base="$(git merge-base "$base_ref" HEAD)"

    git diff "${summary_merge_base}...HEAD" -- >"$tmp_diff"
    numstat_data="$(git diff --numstat "${summary_merge_base}...HEAD" -- || true)"
    notes="reviewing current branch changes against ${base_ref}"
    ;;
  range)
    [[ -n "$from_ref" ]] || {
      echo "Error: range mode requires --from <ref>." >&2
      exit 1
    }
    [[ -n "$to_ref" ]] || {
      echo "Error: range mode requires --to <ref>." >&2
      exit 1
    }
    ref_exists "$from_ref" || {
      echo "Error: from ref '$from_ref' does not exist." >&2
      exit 1
    }
    ref_exists "$to_ref" || {
      echo "Error: to ref '$to_ref' does not exist." >&2
      exit 1
    }

    summary_base="$from_ref"
    summary_head="$to_ref"

    git diff "$from_ref" "$to_ref" -- >"$tmp_diff"
    numstat_data="$(git diff --numstat "$from_ref" "$to_ref" -- || true)"
    notes="reviewing explicit ref range"
    ;;
esac

changed_files="$(count_files "$numstat_data")"
insertions="$(sum_insertions "$numstat_data")"
deletions="$(sum_deletions "$numstat_data")"

if [[ "$changed_files" -eq 0 ]]; then
  status="no_changes"
  notes="${notes}"$'\n'"no diff found for the selected review scope"
fi

echo "=== CODE_REVIEW_SUMMARY ==="
echo "mode: $mode"
echo "repo: $repo_root"
echo "status: $status"
echo "base: $summary_base"
echo "head: $summary_head"
if [[ -n "$summary_merge_base" ]]; then
  echo "merge_base: $summary_merge_base"
fi
echo "changed_files: $changed_files"
echo "insertions: $insertions"
echo "deletions: $deletions"
echo "untracked_files:"
if [[ "$mode" == "workspace" ]]; then
  print_list "$untracked_items" "(none)"
else
  echo "- (not applicable)"
fi
echo "notes:"
print_list "$notes" "(none)"
echo
echo "=== CODE_REVIEW_DIFF ==="
cat "$tmp_diff"
