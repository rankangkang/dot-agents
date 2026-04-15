#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
RESOLVER="${REPO_ROOT}/.agents/skills/code-review/scripts/resolve-review-scope.sh"

TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "${TMP_ROOT}"' EXIT

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

assert_contains() {
  local haystack="$1"
  local needle="$2"

  [[ "$haystack" == *"$needle"* ]] || fail "expected output to contain: ${needle}"
}

assert_not_contains() {
  local haystack="$1"
  local needle="$2"

  [[ "$haystack" != *"$needle"* ]] || fail "expected output to omit: ${needle}"
}

commit_all() {
  local message="$1"

  GIT_AUTHOR_NAME="Test User" \
  GIT_AUTHOR_EMAIL="test@example.com" \
  GIT_COMMITTER_NAME="Test User" \
  GIT_COMMITTER_EMAIL="test@example.com" \
    git add . &&
    GIT_AUTHOR_NAME="Test User" \
    GIT_AUTHOR_EMAIL="test@example.com" \
    GIT_COMMITTER_NAME="Test User" \
    GIT_COMMITTER_EMAIL="test@example.com" \
      git commit -m "$message" >/dev/null
}

create_fixture_repo() {
  local repo_dir="$1"

  mkdir -p "$repo_dir"

  (
    cd "$repo_dir"
    git init >/dev/null
    git checkout -b main >/dev/null

    printf 'base\n' > tracked.txt
    printf 'keep\n' > filtered.txt
    commit_all "initial commit"

    git checkout -b feature >/dev/null

    printf 'base\nworkspace change\n' > tracked.txt
    printf 'keep\nfiltered change\n' > filtered.txt
    printf 'not tracked\n' > untracked.txt
  )
}

run_resolver() {
  local repo_dir="$1"
  shift

  (
    cd "$repo_dir"
    bash "$RESOLVER" "$@"
  )
}

assert_equals() {
  local actual="$1"
  local expected="$2"

  [[ "$actual" == "$expected" ]] || fail "expected '${expected}', got '${actual}'"
}

TEST_REPO="${TMP_ROOT}/fixture-repo"
create_fixture_repo "$TEST_REPO"

default_output="$(run_resolver "$TEST_REPO")"
assert_contains "$default_output" "=== CODE_REVIEW_SUMMARY ==="
assert_contains "$default_output" "mode: workspace"
assert_contains "$default_output" "head: workspace"
assert_contains "$default_output" "=== CODE_REVIEW_FILES ==="
assert_contains "$default_output" "untracked files are excluded from the main diff by default"
assert_not_contains "$default_output" "=== CODE_REVIEW_DIFF ==="
echo "ok - defaults to workspace summary output"

diff_output="$(run_resolver "$TEST_REPO" --diff-only)"
assert_contains "$diff_output" "=== CODE_REVIEW_DIFF ==="
assert_contains "$diff_output" "diff --git"
assert_not_contains "$diff_output" "=== CODE_REVIEW_SUMMARY ==="
echo "ok - diff-only suppresses summary payload"

set +e
conflict_output="$(run_resolver "$TEST_REPO" --summary-only --diff-only 2>&1)"
conflict_status=$?
set -e
assert_equals "$conflict_status" "1"
assert_contains "$conflict_output" "Error: choose at most one of --summary-only or --diff-only."
echo "ok - conflicting output flags fail fast"

branch_output="$(run_resolver "$TEST_REPO" --mode branch --base main)"
assert_contains "$branch_output" "=== CODE_REVIEW_SUMMARY ==="
assert_contains "$branch_output" "mode: branch"
assert_contains "$branch_output" "base: main"
assert_contains "$branch_output" "head: HEAD"
assert_contains "$branch_output" "reviewing current branch changes against main"
echo "ok - branch mode also defaults to summary output"

pathspec_output="$(run_resolver "$TEST_REPO" -- "filtered.txt")"
assert_contains "$pathspec_output" "pathspec: filtered.txt"
assert_contains "$pathspec_output" "changed_files: 1"
assert_contains "$pathspec_output" $'1\t0\tfiltered.txt'
assert_not_contains "$pathspec_output" "tracked.txt"
echo "ok - pathspec filters the summary file list"

echo "All resolve-review-scope tests passed."
