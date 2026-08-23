---
name: triage-issues
description: Read GitHub issues (authored by rgantt only), categorize by workflow state, and advance the newest one (triage -> plan -> implement -> PR)
user-invocable: true
disable-model-invocation: false
argument-hint: [issue number to target, or blank for newest]
---

# Issue Triage & Execution

Read all open GitHub issues **authored by `rgantt`**, categorize them by workflow state, and advance the newest one through the pipeline: **created -> planned -> in progress -> in review**.

Issues authored by other users are displayed for context but never acted on.

## Workflow Labels

Issues move through four states, tracked by GitHub labels:

| Label | Meaning | Next action |
|-------|---------|-------------|
| *(none)* | Raw issue, just filed | Review for clarity, apply `created` |
| `created` | Triaged and accepted | Write implementation plan, apply `planned` |
| `planned` | Plan exists | Implement with tests, apply `in progress` |
| `in progress` | Implementation complete | Create PR, apply `in review` |

## Setup

```bash
# Verify gh CLI is authenticated
gh auth status
```

## Execution

### Step 1: Read and categorize all open issues

```bash
gh issue list --repo DeckDumpster/deckdumpster --state open --json number,title,labels,createdAt,body,author --limit 100
```

Categorize each issue by its label:
- Has label `in review` -> in review
- Has label `in progress` -> in progress
- Has label `planned` -> planned
- Has label `created` -> created
- Has none of the above -> uncategorized (needs triage)

Print a summary table of all issues grouped by state. Mark issues not authored by `rgantt` with `(other)` — these are visible but not actionable.

### Step 2: Select the target issue

If `$ARGUMENTS` contains an issue number, use that (must be authored by `rgantt`). Otherwise, pick the **newest** issue authored by `rgantt` that is not yet `in review`.

If no eligible issues exist, print the summary and stop.

### Step 3: Advance the issue one step

Execute the transition for the issue's current state:

---

#### Transition: *(uncategorized)* -> `created`

The issue has no workflow label. Review it:

1. Read the issue body carefully
2. Check if it's clear enough to act on:
   - Does it describe a specific problem or feature gap?
   - Is there enough context to understand what "done" looks like?
   - Is it a duplicate of an existing issue? (Check other open issues)
3. If unclear, add a comment asking for clarification and apply the `question` label — do NOT apply `created`
4. If it's a duplicate, close it with a comment linking to the original and apply `duplicate`
5. If clear and actionable:
   - Add a comment confirming the issue is accepted and summarizing your understanding
   - Apply the `created` label
   - Apply `bug` or `enhancement` label as appropriate

```bash
gh issue edit <NUMBER> --add-label "created" --repo DeckDumpster/deckdumpster
gh issue comment <NUMBER> --body "<your triage comment>" --repo DeckDumpster/deckdumpster
```

---

#### Transition: `created` -> `planned`

The issue is accepted but has no plan. Create one:

1. Read the issue body and any comments
2. Read the relevant source code to understand the current state
3. Consult `CLAUDE.md` for architecture guidance
4. Write an implementation plan covering:
   - **Approach**: What changes are needed and where
   - **Files to modify**: List specific files and what changes each needs
   - **New files** (if any): What they contain and why they're needed
   - **Testing strategy**: What tests to add/modify, what to assert. If UI changes are involved, note that `/qa-finish` will be needed after implementation.
   - **Edge cases**: What could go wrong, what needs special handling
   - **Scope boundaries**: What this does NOT include
5. Post the plan as a comment on the issue
6. Apply the `planned` label

```bash
gh issue edit <NUMBER> --add-label "planned" --repo DeckDumpster/deckdumpster
gh issue comment <NUMBER> --body "$(cat <<'EOF'
## Implementation Plan

### Approach
...

### Files to modify
...

### Testing strategy
...

### Edge cases
...

### Out of scope
...
EOF
)" --repo DeckDumpster/deckdumpster
```

---

#### Transition: `planned` -> `in progress`

The issue has a plan. Implement it:

1. Read the issue body, comments, and the implementation plan
2. Create a feature branch:
   ```bash
   git checkout -b issue-<NUMBER>-<short-slug> main
   ```
3. Implement the changes following the plan
4. Follow all conventions in `CLAUDE.md`:
   - Always use `uv` for Python operations
   - NEVER add fallback logic — errors should propagate visibly
   - Store data in the local DB, no runtime network calls
   - Use repository pattern from `models.py`
   - Follow schema migration conventions in `schema.py`
5. Run the test suite:
   ```bash
   uv run pytest
   uv run ruff check mtg_collector/
   ```
6. If UI changes were made, run `/qa-finish` to generate UI scenario tests
7. Apply the `in progress` label

```bash
gh issue edit <NUMBER> --add-label "in progress" --repo DeckDumpster/deckdumpster
```

**IMPORTANT constraints during implementation:**
- Do not make changes outside the scope of the plan — if scope needs to expand, update the plan comment first
- Follow the data model conventions (join chain, JSON-as-TEXT columns, price joins on set_code+collector_number)
- Test fixture may need regeneration after schema changes (`uv run python scripts/build_test_fixture.py`)

---

#### Transition: `in progress` -> `in review`

The implementation is complete. Create a PR:

1. Verify all tests pass (re-run the full suite)
2. Review your own changes:
   ```bash
   git diff main...HEAD
   ```
3. Ensure the branch is pushed:
   ```bash
   git push -u origin HEAD
   ```
4. Create the PR linking to the issue:
   ```bash
   gh pr create --title "<concise title>" --body "$(cat <<'EOF'
   ## Summary
   <what this PR does>

   Closes #<NUMBER>

   ## Changes
   <bulleted list of changes>

   ## Test plan
   <how this was tested>

   🤖 Generated with [Claude Code](https://claude.com/claude-code)
   EOF
   )" --repo DeckDumpster/deckdumpster
   ```
5. Apply `in review` label to the issue

```bash
gh issue edit <NUMBER> --add-label "in review" --repo DeckDumpster/deckdumpster
```

**Do NOT create a PR unless:**
- The issue has a `planned` label (plan was written and posted)
- All tests pass (`uv run pytest` + `uv run ruff check mtg_collector/`)
- The implementation matches the plan (or the plan was updated to reflect changes)

---

## Output

After advancing the issue, print a summary:

```
## Triage Summary

### All Open Issues (rgantt only)
| # | Title | State |
|---|-------|-------|

### Other Open Issues (not actionable)
| # | Title | Author |
|---|-------|--------|

### Action Taken
- Issue: #<NUMBER> — <title>
- Previous state: <old state>
- New state: <new state>
- What was done: <1-2 sentence summary>
```

$ARGUMENTS
