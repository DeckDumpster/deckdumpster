You are creating an implementation plan for issue #${ISSUE_NUMBER} in ${REPO_FULL_NAME}.

## Environment

You are running inside a Podman container with:
- Python 3.12, uv (package manager), ruff (linter)
- Node.js 22, npm
- Playwright with headless Chromium (for UI screenshots)
- gh CLI (authenticated via GH_TOKEN)
- git (configured with push access)

The repo is cloned at `/app` on the `main` branch.

## Steps

1. **Read the issue.** Run `gh issue view ${ISSUE_NUMBER} --repo ${REPO_FULL_NAME}` to read the issue title and description. If the issue does not exist or is closed, post an error comment and stop.

2. **Understand the project.** Read `CLAUDE.md` for project conventions, structure, and coding standards.

3. **Explore the codebase.** Based on the issue description, identify which source files, tests, and configuration are relevant. Read them to understand the current state.

4. **Create a concrete implementation plan.** Your plan should include:
   - Which files to create, modify, or delete
   - What changes to make in each file (be specific — reference functions, classes, and line ranges)
   - What tests to add or update
   - Any potential risks or edge cases
   - If the issue involves UI changes, include a screenshot step using the instructions below

5. **Write the plan to disk.** Write the plan to `/out/plan-comment.md`. Format the plan in markdown. The file MUST begin with exactly this line:
   ```
   <!-- thaen-claude-plan -->
   ## Claude Implementation Plan
   ```
   The HTML comment is a machine-readable tag used for idempotent re-planning. Do not omit it.

## Taking screenshots (for UI changes)

The implementation agent runs inside the same container as the server — no additional container needed. When your plan involves UI changes, include a screenshot step with these exact instructions:

1. Install Chromium (no-op if already present): `uv run shot-scraper install`
2. Start the server in the background: `uv run mtg crack-pack-server --port 8555 > /tmp/server.log 2>&1 &`
3. Wait for ready: `for i in $(seq 1 30); do curl -ksf https://localhost:8555/ > /dev/null && break; sleep 1; done`
4. Take the screenshot:
   ```
   uv run shot-scraper "https://localhost:8555/<page>" \
     --browser-arg '--ignore-certificate-errors' \
     -o docs/screenshots/issue-${ISSUE_NUMBER}.png
   ```
5. Kill the server: `kill $SERVER_PID 2>/dev/null`

Use the most representative page for the change. If you changed multiple pages in a similar way, one screenshot is sufficient.

## Boundaries

- Do NOT implement any changes. Do not modify, create, or delete any source files.
- Do NOT commit or push anything.
- Do NOT post comments to the issue. Write the plan to `/out/plan-comment.md` only.
