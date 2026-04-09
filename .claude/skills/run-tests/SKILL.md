---
name: run-tests
description: Run the project test suites with real-time progress monitoring. Runs tiers in order of speed and stops on failure.
user-invocable: true
disable-model-invocation: false
argument-hint: "[tier] [--instance name] [-k pattern]"
---

# Run Tests

Run the test suites with real-time progress monitoring via a JSONL progress file. Tests are organized into tiers by speed and dependencies.

## Arguments

- `$ARGUMENTS` — optional tier name, instance, and/or `-k` pattern
  - No args: run tier 1 (unit tests) only
  - `all`: run tiers 1-3 (unit + integration + scryfall). Requires a running container.
  - `all --instance <name>`: same, specifying which container instance
  - `ui` or `ui --instance <name>`: run tier 4 (UI scenario tests)
  - `1`, `2`, `3`, `4`: run a specific tier
  - `-k <pattern>`: pass through to pytest (works with any tier)
  - `full --instance <name>`: run all 4 tiers sequentially

## Tiers

| Tier | Name | Command | Deps | Time |
|------|------|---------|------|------|
| 1 | Unit + generative | `uv run pytest tests/ --ignore=tests/ui --ignore=tests/integration` | None | ~2.5 min |
| 2 | Integration | `uv run pytest tests/integration/ --instance <name>` | Container | ~10s |
| 3 | Scryfall comparison | `uv run pytest tests/test_search_scryfall.py tests/test_search_generative.py --scryfall` | Network (first run only) | ~30s cached |
| 4 | UI scenarios | `uv run pytest tests/ui/ --instance <name>` | Container + API key | ~17 min |

Always-skipped (not in any tier): 7 order parser tests need real vendor HTML files.

## How to Run

### 1. Parse arguments

Extract tier, instance name, and any `-k` pattern from `$ARGUMENTS`. Default tier is `1`. Default instance is `integration-test`.

### 2. Pre-flight checks

- For tiers 2 and 4: verify the container is running via `podman container exists systemd-mtgc-<instance>`. If not running, report the setup command and stop.
- For tier 3: no pre-flight needed (Scryfall cache handles cold start transparently).

### 3. Run with progress monitoring

For each tier, run the pytest command in the background **without any pipes** (critical — pipes buffer output and break progress monitoring):

```bash
uv run pytest <args> -v --tb=short 2>&1
```

The `run_in_background` flag sends output to a file. The progress file at `/tmp/pytest-progress.jsonl` is written in real time by a conftest hook (every test result is flushed immediately).

### 4. Monitor progress

While waiting for the background command, periodically read the progress file to report status:

```bash
# Count results so far
grep -c '"event": "test_result"' /tmp/pytest-progress.jsonl

# See the last few results
tail -5 /tmp/pytest-progress.jsonl

# Check for failures
grep '"outcome": "failed"' /tmp/pytest-progress.jsonl
```

Report progress to the user at natural milestones (every ~25% or when failures appear). Use the `Read` tool on the progress file, not `cat` piped through grep.

### 5. Report results

When the background command completes, read the full output file and report:

- Total passed / failed / skipped / errors
- List any failures with their nodeid
- Wall clock time
- Whether to proceed to the next tier (stop on failure unless user said `full`)

## Progress File Format

Written to `/tmp/pytest-progress.jsonl` (override via `PYTEST_PROGRESS_FILE` env var). Each line is JSON:

```jsonl
{"event": "session_start", "collected": 0, "ts": 1234567890.0}
{"event": "collected", "total": 150, "ts": 1234567890.1}
{"event": "test_result", "nodeid": "tests/test_foo.py::test_bar", "outcome": "passed", "duration": 0.05, "elapsed": 1.2}
{"event": "test_result", "nodeid": "tests/test_foo.py::test_baz", "outcome": "failed", "duration": 0.10, "elapsed": 1.5}
{"event": "session_end", "exitstatus": 1, "elapsed": 2.0, "ts": 1234567892.0}
```

## Key Rules

- **NEVER pipe background commands** through `tail`, `head`, or `grep`. This buffers all output until process completion, making progress invisible.
- Always use `-v --tb=short` for readable output.
- The progress file is the primary monitoring mechanism. The background output file is the secondary source (has full pytest output).
- Stop on first tier failure unless `full` was requested.
- For tier 4 (UI), report individual scenario pass/fail as they come in — these are expensive (~5s each with Claude API calls).
