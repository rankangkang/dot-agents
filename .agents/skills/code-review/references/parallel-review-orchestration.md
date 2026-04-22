# Parallel Review Orchestration

Parent-agent guide for splitting a large code review scope across multiple sub-agents and aggregating their findings.

Do not ask child review sub-agents to load this document. Child agents should receive only bounded-scope review instructions plus the relevant review checklists.

## Non-Negotiable Rules

For the parent agent:
- Use `scripts/resolve-review-scope.sh` as the only source of truth for review scope discovery and diff retrieval.
- Always run the resolver with `--summary-only` before deciding whether to stay single-pass or dispatch sub-agents.
- Do not replace resolver-based scope discovery with raw `git diff`, `git status`, or `git log` unless the resolver cannot be found or exits non-zero.

For child review sub-agents:
- Review only the assigned path group.
- Do not split the scope further.
- Do not dispatch additional sub-agents.
- Do not use raw `git diff`, `git status`, or `git log` to discover scope when the resolver command is available.
- Return findings only, plus cross-module risks if noticed.

## When to Use

- Use this flow when `diff_lines_estimate > 1000`.
- Keep single-pass review for smaller diffs to avoid unnecessary coordination overhead.

## Goals

- Preserve review quality on large diffs without exhausting context windows.
- Keep each sub-agent focused on a bounded, coherent module scope.
- Reconstruct a single final review that is deduplicated and prioritized by risk.

## Step 1: Group Files by Module

Use `=== CODE_REVIEW_FILES ===` from the scope resolver to create review groups.

- Target roughly `<= 1000` estimated changed lines per group.
- Keep closely related files together, such as implementation plus tests, service plus types, or API route plus validators.
- If one file is larger than the threshold by itself, let it form a single-file group and review it with extra care for truncation risk.
- Prefer logical module boundaries over raw alphabetical or file-order splits.

## Step 2: Write Cross-Cutting Context Notes

Before launching sub-agents, identify changes that may affect multiple groups.

Common cross-cutting signals:
- Interface or shared type changes
- Shared utility or helper updates
- Configuration, schema, or migration changes
- Public API surface changes
- Shared state or concurrency-sensitive logic

Pass the same cross-cutting notes to every sub-agent so they can evaluate local changes against shared risks.

## Step 3: Launch Review Sub-Agents

Use the `Subagent` tool with `subagent_type="generalPurpose"` and `readonly=true`.

### Suggested Call Shape

Copy this prompt with minimal edits so the imperative constraints stay intact.

```json
{
  "description": "review auth module",
  "subagent_type": "generalPurpose",
  "readonly": true,
  "model": "fast",
  "prompt": "You are performing a bounded-scope code review.\n\nYou MUST use the provided resolver command as the source of truth for scope discovery and diff retrieval. Do NOT replace it with raw git diff, git status, or git log commands unless the resolver command fails.\n\nFirst, load and follow these review checklists:\n- /abs/path/.agents/skills/code-review/references/solid-checklist.md\n- /abs/path/.agents/skills/code-review/references/security-checklist.md\n- /abs/path/.agents/skills/code-review/references/code-quality-checklist.md\n- /abs/path/.agents/skills/code-review/references/removal-plan.md\n\nThen run exactly this scope command:\nbash \"/abs/path/.agents/skills/code-review/scripts/resolve-review-scope.sh\" --mode branch --base main --diff-only -- path/to/module path/to/shared-file.ts\n\nCross-cutting context:\n- shared auth types changed\n- public API contract may affect callers outside this module\n\nInstructions:\n1. Review only this assigned scope, using the resolver output diff as the source of truth.\n2. Do not split the scope further and do not dispatch additional sub-agents.\n3. Expand into nearby code only when needed to validate contracts or behavior.\n4. Check SOLID, architecture, removal candidates, security/reliability, and code quality.\n5. Return findings only, grouped by severity (P0/P1/P2/P3).\n6. Include any cross-module risks you notice.\n7. Do not implement fixes and do not write an overall summary.\n8. If the resolver command cannot be executed successfully, report that failure instead of falling back to ad-hoc scope discovery."
}
```

### Adaptation Rules

- Replace `--mode branch --base main` with `workspace` or `range` inputs when needed.
- Keep `--diff-only` in child-agent scope commands so the response contains only review payload.
- Replace the example paths with the current file group.
- Keep `description` short and identifiable by module or path group.
- Be explicit about scope boundaries so different sub-agents do not duplicate work.
- Keep orchestration logic in the parent agent; child agents should only review their assigned scope.

## Step 4: Aggregate and Cross-Check

Parallel review is not complete until the parent agent performs an explicit aggregation pass after all sub-agents return.

The aggregation pass must:
- Confirm how many sub-agent result groups were received.
- Confirm deduplication was performed.
- Confirm cross-module consistency checks were performed.
- State whether any new cross-module findings were added during aggregation.
- Then produce the final review report.

After the explicit aggregation pass:

- Merge findings into one numbered list.
- Deduplicate overlapping findings that describe the same root cause.
- Re-prioritize severity when two agents disagree; keep the highest justified severity.
- Add new findings when a risk only becomes visible after combining multiple groups.
- Produce the final report in the main skill's output format.

### Suggested Parent-Agent Aggregation Prompt

```text
You are aggregating findings from multiple code-review sub-agents.

Inputs:
- Review mode: <workspace|branch|range>
- Scope summary: <HEAD -> workspace / base...HEAD / from -> to>
- Cross-cutting context:
  - <note 1>
  - <note 2>
- Sub-agent findings:
  - Group A: <findings>
  - Group B: <findings>
  - Group C: <findings>

Tasks:
1. Merge all findings into a single numbered list.
2. Deduplicate overlapping findings that describe the same root cause.
3. Re-prioritize severity when multiple findings conflict; prefer the highest justified severity.
4. Add new cross-module findings when the risk only becomes visible after combining groups.
5. Keep concrete, actionable descriptions and suggested fixes.
6. Produce the final report using the step 8 format.

Cross-module checks:
- Were callers updated when shared interfaces or types changed?
- Did naming or conventions drift across modules?
- Were shared state, concurrency, config, or API boundary risks introduced?
- Did one module add validation or error-handling assumptions that another module does not satisfy?

Rules:
- Do not repeat the same issue across multiple files unless the fixes are materially different.
- Prefer root-cause framing over symptom lists.
- Preserve evidence that helps the user fix the issue quickly.
- If no findings remain after deduplication, explicitly state what was checked and any residual risks.
```

## Aggregation Heuristics

- Merge duplicates when two findings point to the same contract break, even if different groups discovered it.
- Keep separate findings when the same pattern appears in different modules but requires different fixes.
- If a sub-agent reports uncertainty, verify it against the combined context before surfacing it as a final finding.
- Prefer a single cross-module finding over several local symptom findings when that makes remediation clearer.
