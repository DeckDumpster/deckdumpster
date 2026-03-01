You are implementing the approved plan for issue #${ISSUE_NUMBER} in ${REPO_FULL_NAME}.

## Environment

You are running inside a Podman container with:
- Python 3.12, uv (package manager), ruff (linter)
- Node.js 22, npm
- Playwright with headless Chromium (for UI screenshots)
- gh CLI (authenticated via GH_TOKEN)
- git (configured with push access)

The repo is at `/app` on a branch called `claude/issue-${ISSUE_NUMBER}` (based on `main`). Everything is pre-installed and ready:
- Project dependencies including dev/test (pytest, ruff, etc.) — do not reinstall them.
- Card database: `$MTGC_DB` points to a writable SQLite copy (already set). `$MTGC_HOME` has supplementary data. The server starts without additional setup — do not run `mtg setup` or any data import commands.

## Constraints

- **Always `Read` a file before editing it.** The `Edit` tool will reject your change if you haven't read the file first. Using `grep` or `wc` does not count.
- Do NOT use `grep`, `cat`, `head`, or `tail` to read files — use the `Read` tool.
- Do NOT reinstall dependencies — everything is pre-installed.
- Do NOT use `git add -A` or `git add .` — stage specific files by path.
- **Bash tool limitation:** Shell state (variables, background PIDs) does NOT persist between separate Bash tool calls. If you need to background a process and interact with it, chain everything with `&&` in a single Bash call. Never use separate Bash calls for `cmd &` then `sleep` then `kill $PID`.

## Steps

1. **Find the plan.** Run `gh issue view ${ISSUE_NUMBER} --repo ${REPO_FULL_NAME} --comments` and look for a comment starting with `## Claude Implementation Plan`. If no plan is found, post a comment saying "No implementation plan found for this issue. Please run the planning phase first." and stop.

2. **Understand the project.** Read `CLAUDE.md` for project conventions, structure, and coding standards.

3. **Implement the plan.** Follow the plan step by step. Adhere to the coding conventions in `CLAUDE.md`.

4. **Run tests and linting.** Execute:
   ```
   uv run pytest
   uv run ruff check $(git diff --name-only main -- '*.py')
   ```
   This lints only files you changed, avoiding pre-existing warnings in other files. If there are failures, fix them and re-run until tests pass and linting is clean.

5. **Screenshot UI changes.** If your changes affect the UI (templates, styles, frontend logic), take a screenshot using `shot-scraper`. Skip this for backend-only changes. If you changed multiple pages similarly, one screenshot of the most representative page is sufficient.

   **CRITICAL: The Bash tool does not persist shell state across calls. You MUST run the server, screenshot, and kill in ONE Bash command joined with `&&`. Do NOT use separate Bash calls. Do NOT use newlines between commands.**

   Copy-paste this exactly (only change `<TARGET_PATH>`, e.g. `/collection`, `/sealed`, `/`):
   ```bash
   cd /app && uv run mtg crack-pack-server --port 8555 > /tmp/server.log 2>&1 & SERVER_PID=$! && for i in $(seq 1 30); do curl -ksf https://localhost:8555/ > /dev/null && break; sleep 1; done && mkdir -p docs/screenshots && uv run shot-scraper "https://localhost:8555/<TARGET_PATH>" --browser-arg '--ignore-certificate-errors' -o docs/screenshots/issue-${ISSUE_NUMBER}.png && kill $SERVER_PID 2>/dev/null
   ```
   Set a **120-second timeout** on this Bash command. If it times out or fails, **skip the screenshot and move on** — do not spend multiple turns debugging server startup. The screenshot is nice-to-have, not a blocker for the PR.

6. **Commit and push.** Stage only the files you changed (use `git add` with specific file paths, not `git add -A`). If you took a screenshot, stage it:
   ```bash
   git add docs/screenshots/issue-${ISSUE_NUMBER}.png
   ```
   Commit with a descriptive message summarizing the changes. Push to the branch `claude/issue-${ISSUE_NUMBER}`.

7. **Open a pull request.** Use:
   ```
   gh pr create --repo ${REPO_FULL_NAME} --title '<descriptive title>' --body '<body referencing issue>'
   ```
   Reference the issue with `Closes #${ISSUE_NUMBER}` in the PR body. If a screenshot was committed, embed it in the PR body using a raw GitHub URL (relative paths don't work in PR descriptions):
   ```
   ![screenshot](https://raw.githubusercontent.com/${REPO_FULL_NAME}/claude/issue-${ISSUE_NUMBER}/docs/screenshots/issue-${ISSUE_NUMBER}.png)
   ```
   Include a brief description of what the screenshot shows.

8. **Post a summary comment on the issue.** Use:
   ```
   gh issue comment ${ISSUE_NUMBER} --repo ${REPO_FULL_NAME} --body '<your summary>'
   ```
   The comment MUST start with the heading `## Claude Implementation Summary`. Include:
   - What was implemented
   - Link to the PR
   - Test results
   - Any deviations from the plan and why

## Before you finish

Verify all of these before stopping:
- `uv run pytest` exits 0
- `uv run ruff check` passes on your changed files
- Your branch is pushed
- A PR is open and references the issue
- A summary comment is posted on the issue
