---
name: code-review
description: "Expert code review of current git changes with a senior engineer lens. Detects SOLID violations, security risks, and proposes actionable improvements."
---

# Code Review

## Overview

Perform a structured review of a selected git diff scope with focus on SOLID, architecture, removal candidates, and security risks. Default to review-only output unless the user asks to implement changes.

## Review Modes

- `workspace` (default): review current tracked workspace changes, including staged and unstaged diffs. Untracked files are listed separately and excluded from the main diff by default.
- `branch`: review the current branch against a target base branch. If `base` is omitted, auto-detect one of `origin/main`, `origin/master`, `main`, or `master`.
- `range`: review an explicit ref range with `from` and `to`.
- `unstaged`: reserved / TBD. Do not use unless the user explicitly asks for it and the skill is extended later.

## Mode Resolution Rules

- If the user explicitly provides `mode`, respect it.
- If the user provides `from` and `to`, use `range`.
- If the user asks to compare the current branch against `main`, `master`, or another named base branch, use `branch`.
- Otherwise, default to `workspace`.
- Treat `unstaged` as reserved and do not select it implicitly.

## Severity Levels

| Level | Name | Description | Action |
|-------|------|-------------|--------|
| **P0** | Critical | Security vulnerability, data loss risk, correctness bug | Must block merge |
| **P1** | High | Logic error, significant SOLID violation, performance regression | Should fix before merge |
| **P2** | Medium | Code smell, maintainability concern, minor SOLID violation | Fix in this PR or create follow-up |
| **P3** | Low | Style, naming, minor suggestion | Optional improvement |

## Workflow

### 1) Find the scope resolver

The CLI lives in the sibling path `scripts/resolve-review-scope.sh`. Because this skill may be exported or distributed through a symlink, first use `Glob` to find the real script path, then call it via an absolute path. Use `$SCOPE` below to refer to that absolute path.

Treat the resolver as a thin protocol wrapper around git: it should standardize mode selection, path filtering, and output shape, not become a second review engine.

```text
**/skills/code-review/scripts/resolve-review-scope.sh
```

### 2) Triage review scope

- Determine the review mode from the user request.
- Default to `workspace` when the user asks for a general review of current changes.
- **Scope resolution is mandatory**: use `scripts/resolve-review-scope.sh` as the source of truth for review scope discovery and diff retrieval. Do not substitute direct `git diff`, `git status`, or `git log` commands unless the resolver cannot be found or exits non-zero.
- **Always start by running the scope resolver with `--summary-only`** to get a lightweight overview before fetching the diff payload:

**Script calls:**
- `bash "$SCOPE" --mode workspace --summary-only`
- `bash "$SCOPE" --mode branch --base main --summary-only`
- `bash "$SCOPE" --mode range --from abc123 --to def456 --summary-only`

**Read the triage output:**
- `=== CODE_REVIEW_SUMMARY ===`: check `diff_lines_estimate` together with `changed_files` to assess scope size.
- `=== CODE_REVIEW_FILES ===`: review the file list with per-file numstat (insertions / deletions / path).

**Choose review strategy based on estimated changed lines:**
- **`diff_lines_estimate <= 1000`** → **Single-pass review** (continue to step 3)
- **`diff_lines_estimate > 1000`** → **Parallel review** (jump to step 3a)

**Edge cases:**
- **No changes**: If the script returns `status: no_changes`, inform the user and ask whether to switch mode or provide a different base/range.
- **Workspace mode with untracked files**: Call out that untracked files are excluded by default and ask whether the user wants to review them separately.

### 3) Single-pass review

Run the scope resolver again with `--diff-only` to get the review payload:

- `bash "$SCOPE" --mode workspace --diff-only`
- `bash "$SCOPE" --mode branch --base main --diff-only`
- `bash "$SCOPE" --mode range --from abc123 --to def456 --diff-only`

**How to use the script output:**
- Treat the `--summary-only` output from step 2 as the source of truth for scope metadata.
- Treat the `--diff-only` output as the source of truth for the review payload.
- Use `rg` to inspect related modules, usages, and contracts only when the diff suggests a dependency or ownership boundary that needs expansion.
- Identify entry points, ownership boundaries, and critical paths (auth, payments, data writes, network).

**Large single-pass diff (500–1000 lines)**: Summarize by file first, then review in batches by module or feature area. Mixed concerns should be grouped by logical feature, not file order.

Proceed to **step 4** for review analysis.

### 3a) Parallel review (large diffs only)

When `diff_lines_estimate > 1000`, split the review across multiple sub-agents to avoid context window exhaustion and maintain review quality.

Before grouping files or dispatching sub-agents, load `references/parallel-review-orchestration.md` and treat it as the parent-agent contract for batching, dispatch, and aggregation.

**1. Group files by module**

Using `=== CODE_REVIEW_FILES ===` from the triage output, group files by top-level directory or logical module:
- Each group should target roughly ≤ 1000 diff lines (use per-file insertions + deletions as estimate).
- Keep closely related files together (e.g., a component and its tests, a service and its types).
- If a single file exceeds 1000 estimated changed lines, it forms its own group and should be reviewed with extra care for truncation risk.

**2. Identify high-propagation changes**

Scan the file list for changes that may ripple across modules:
- Interface / type definition files
- Shared utility / helper functions
- Configuration or schema files
- Public API surface changes

Summarize these as **cross-cutting context notes** to include in every sub-agent's prompt.

**3. Dispatch sub-agents**

For each file group, spawn a sub-agent with the `Subagent` tool, `subagent_type="generalPurpose"`, and `readonly=true`.

Each sub-agent prompt should include:
- The scope resolver path (`$SCOPE`) and the exact command to run with path filter:
  ```
  bash "$SCOPE" --mode <mode> [--base <base>] [--from <ref> --to <ref>] --diff-only -- <path1> <path2> ...
  ```
- Paths to the reference checklists (`references/solid-checklist.md`, `references/security-checklist.md`, `references/code-quality-checklist.md`, `references/removal-plan.md`) — instruct the sub-agent to load and follow them.
- The cross-cutting context notes from step 2.
- Instruction to perform review analysis (steps 4–7) and output findings using the structured format from step 8 (findings section only, no overall summary).
- Make the scope boundary explicit: review only the assigned path group, do not split the scope further, and do not dispatch additional sub-agents.
- Make the scope-discovery rule explicit: do not use raw `git diff`, `git status`, or `git log` to discover review scope when the resolver command is available.

Launch sub-agents **in parallel** when groups are independent.

When creating each sub-agent call:
- Set a short `description` that identifies the module or path group.
- Set `readonly=true` explicitly so large-diff review stays review-only unless the user later asks for implementation.
- Ask the sub-agent to return only structured findings plus any cross-module risks it noticed.
- Prefer copying the bounded-scope prompt contract from `references/parallel-review-orchestration.md` with minimal edits so the non-negotiable constraints remain intact.

**4. Explicit aggregation and cross-check**

Parallel review is not complete until the parent agent performs an explicit aggregation pass after all sub-agents return.

The aggregation step must:
- Confirm how many sub-agent result groups were received.
- Confirm deduplication was performed.
- Confirm cross-module consistency checks were performed.
- State whether any new cross-module findings were added during aggregation.
- Then produce the final review report using step 8.

After the explicit aggregation pass:
- Merge findings into a single list, deduplicate, and re-prioritize.
- Perform **cross-module consistency check**:
  - Interface contracts: are callers updated when signatures change?
  - Naming and conventions: consistent across modules?
  - Shared state: any concurrent access issues introduced?
- Add any cross-module findings as additional items.
- Load `references/parallel-review-orchestration.md` for the parent-agent aggregation prompt and deduplication heuristics.
- Produce the final report per step 8.

Skip to **step 8** for output format.

### 4) SOLID + architecture smells

- Load `references/solid-checklist.md` for specific prompts.
- Use the resolved diff as the primary review scope and expand into neighboring code only when required to validate contracts or behavior.
- Look for:
  - **SRP**: Overloaded modules with unrelated responsibilities.
  - **OCP**: Frequent edits to add behavior instead of extension points.
  - **LSP**: Subclasses that break expectations or require type checks.
  - **ISP**: Wide interfaces with unused methods.
  - **DIP**: High-level logic tied to low-level implementations.
- When you propose a refactor, explain *why* it improves cohesion/coupling and outline a minimal, safe split.
- If refactor is non-trivial, propose an incremental plan instead of a large rewrite.

### 5) Removal candidates + iteration plan

- Load `references/removal-plan.md` for template.
- Identify code that is unused, redundant, or feature-flagged off.
- Distinguish **safe delete now** vs **defer with plan**.
- Provide a follow-up plan with concrete steps and checkpoints (tests/metrics).

### 6) Security and reliability scan

- Load `references/security-checklist.md` for coverage.
- Check for:
  - XSS, injection (SQL/NoSQL/command), SSRF, path traversal
  - AuthZ/AuthN gaps, missing tenancy checks
  - Secret leakage or API keys in logs/env/files
  - Rate limits, unbounded loops, CPU/memory hotspots
  - Unsafe deserialization, weak crypto, insecure defaults
  - **Race conditions**: concurrent access, check-then-act, TOCTOU, missing locks
- Call out both **exploitability** and **impact**.

### 7) Code quality scan

- Load `references/code-quality-checklist.md` for coverage.
- Check for:
  - **Error handling**: swallowed exceptions, overly broad catch, missing error handling, async errors
  - **Performance**: N+1 queries, CPU-intensive ops in hot paths, missing cache, unbounded memory
  - **Boundary conditions**: null/undefined handling, empty collections, numeric boundaries, off-by-one
- Flag issues that may cause silent failures or production incidents.

### 8) Output format

Structure your review as follows:

```markdown
## Code Review Summary

**Review mode**: [workspace / branch / range]
**Scope**: [HEAD -> workspace / base...HEAD / from -> to]
**Files reviewed**: X files, Y lines changed
**Overall assessment**: [APPROVE / REQUEST_CHANGES / COMMENT]

---

## Findings

### P0 - Critical
(none or list)

### P1 - High
1. **[file:line]** Brief title
  - Description of issue
  - Suggested fix

### P2 - Medium
2. (continue numbering across sections)
  - ...

### P3 - Low
...

---

## Removal/Iteration Plan
(if applicable)

## Additional Suggestions
(optional improvements, not blocking)
```

**Inline comments**: Use this format for file-specific findings:
```
::code-comment{file="path/to/file.ts" line="42" severity="P1"}
Description of the issue and suggested fix.
::
```

**Clean review**: If no issues found, explicitly state:
- What was checked
- Any areas not covered (e.g., "Did not verify database migrations")
- Residual risks or recommended follow-up tests

### 9) Next steps confirmation

After presenting findings, ask user how to proceed:

```markdown
---

## Next Steps

I found X issues (P0: _, P1: _, P2: _, P3: _).

**How would you like to proceed?**

1. **Fix all** - I'll implement all suggested fixes
2. **Fix P0/P1 only** - Address critical and high priority issues
3. **Fix specific items** - Tell me which issues to fix
4. **No changes** - Review complete, no implementation needed

Please choose an option or provide specific instructions.
```

**Important**: Do NOT implement any changes until user explicitly confirms. This is a review-first workflow.

## Resources

### scripts/

| File | Purpose |
|------|---------|
| `scripts/resolve-review-scope.sh` | Resolve the selected review scope and output either summary/file list or diff payload |

### references/

| File | Purpose |
|------|---------|
| `solid-checklist.md` | SOLID smell prompts and refactor heuristics |
| `security-checklist.md` | Web/app security and runtime risk checklist |
| `code-quality-checklist.md` | Error handling, performance, boundary conditions |
| `removal-plan.md` | Template for deletion candidates and follow-up plan |
| `parallel-review-orchestration.md` | Large diff batching, sub-agent prompts, and aggregation heuristics |
