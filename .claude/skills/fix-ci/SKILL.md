---
name: fix-ci
description: Diagnose and fix a failing CI run on the self-hosted runner. Treats CI failures as your responsibility to root-cause, never as flakes.
user-invocable: true
disable-model-invocation: false
argument-hint: "[pr-number | run-id]"
---

# Fix CI

## Read this first — the mindset

**You are running on the exact same machine as the CI runner.** GitHub Actions for `DeckDumpster/deckdumpster` execute on a self-hosted runner at `/home/ryangantt/github-runner-setup/actions-runner/_work/deckdumpster/deckdumpster`. This means:

- **Every CI failure is your responsibility.** Local state you (or a previous Claude session) created — disk usage, leftover containers, lingering processes, occupied ports, stale caches — directly causes CI failures.
- **There are no "flakes" on this runner.** If a job times out, runs out of memory, or hits a "network" error, it is almost always because the local machine is in a bad state.
- **Do not re-run CI hoping it passes.** Re-running before diagnosing is forbidden. The same broken state will produce the same failure, just wasting more time.
- **Diagnose deeply before acting.** Read the actual log lines that mention the failure. Trace them to a system-level cause (disk, memory, podman, network, ports). Only then propose a fix.
- **You are the senior engineer on call.** A junior would shrug and re-run. Don't.

If you find yourself typing the words "transient", "flake", "intermittent", or "let's just retry" — stop. You are wrong. Go back and diagnose.

## Arguments

- `$1` — optional PR number, branch name, or workflow run ID
  - If a number ≤ 10000: treat as PR number (`gh pr checks <n>`)
  - If a longer number: treat as workflow run ID (`gh run view <n>`)
  - If absent: get the failing run for the current branch (`gh run list --branch $(git branch --show-current) --limit 1`)

## Phase 1 — Identify the failing run

```bash
# Resolve the failing run ID
gh run list --branch <branch> --limit 5
gh pr checks <pr> # if PR number was given
```

Get the run ID, the failing job, and the time of failure. Note which step failed.

## Phase 2 — Read the failure log carefully

```bash
gh run view <run-id> --log-failed
```

Read the full failing-step output. Quote the **specific error line(s)** to yourself before doing anything else. Common patterns and what they actually mean:

| Error pattern | Real cause (almost always) |
|---|---|
| `uv` / `pip` `operation timed out` downloading a package | Disk full or thrashing — not network |
| `io: read/write on closed pipe` during podman build | Disk full mid-layer-write |
| `no space left on device` | Disk full (obviously) |
| `cannot allocate memory`, `OOMKilled`, killed at random | Memory pressure from other processes |
| `address already in use`, `bind: address in use` | Stale container/process holding the port |
| `Error: container with name ... already exists` | Previous test container not torn down |
| `lock file held by another process` | Another podman/uv/apt process running |
| Container fails to start, journal shows nothing | Quadlet unit broken or systemd-user state stale |
| Test hangs and times out | Background process competing for CPU/disk, or leftover container holding a DB lock |
| Pytest fails with `database is locked` | Stale sqlite connection from a leftover instance |
| `permission denied` writing to `/home/ryangantt/...` | Container ran as wrong user, or filesystem readonly because full |

**Do not skip this step.** Quote the actual error and write down which row of the table it matches.

## Phase 3 — Inspect local system state

Run these one at a time, never as a `&&`-chained block:

```bash
df -h /home /tmp /var       # disk
free -h                     # memory + swap
podman ps -a                # all containers, including stopped
podman volume ls            # volumes
podman images               # images
systemctl --user list-units 'mtgc-*' --all   # quadlet units
ss -ltnp | grep -E '8081|8080'  # listening ports CI uses
```

Then check the usual disk-space culprits when disk is tight (>85% used):

```bash
du -sh /home/ryangantt/workspace/efj-mtgc/screenshots 2>/dev/null
du -sh /home/ryangantt/workspace/efj-mtgc/.venv 2>/dev/null
du -sh /home/ryangantt/.cache/uv 2>/dev/null
du -sh /home/ryangantt/.cache/ms-playwright 2>/dev/null
du -sh /home/ryangantt/.local/share/containers 2>/dev/null
du -sh /home/ryangantt/workspace/efj-mtgc-* 2>/dev/null
```

Known accumulation points (have caused CI failures before):
- **`~/workspace/efj-mtgc/screenshots/ui/`** — UI test runs leave 30MB+ per run here. 247 dirs ≈ 7.7G. Gitignored, safe to delete.
- **`~/.cache/uv`** — uv package cache, can grow to 6+ GB. Use `uv cache prune` to compact safely; full delete forces redownload but is fine.
- **`~/.cache/ms-playwright`** — Chromium downloads, ~600 MB. Don't delete unless desperate.
- **`~/workspace/efj-mtgc-issue*/.venv`** — sibling worktrees from old issue branches, often abandoned. Each is ~1–5 GB. Confirm worktree is dead before deleting.
- **`~/.local/share/containers/`** — podman storage; prune with `podman system prune -a` (CONFIRM with user before doing this — it's destructive to images they may still want).
- **Stale `mtgc-<instance>` containers/volumes** from test deploys that weren't torn down.

## Phase 4 — Form a hypothesis and confirm it

Tie the error from Phase 2 to the system state from Phase 3. Write the hypothesis out in one sentence: "CI failed at step X with error Y, which is caused by local condition Z (evidence: ...)".

If you cannot connect the failure to a concrete local cause, **dig deeper before acting**. Re-read the log, check `journalctl --user -u mtgc-<instance> --since '1 hour ago'`, inspect the work tree under `_work/deckdumpster/deckdumpster`, look at `~/.local/share/containers/storage/overlay/` for partial layers, etc.

Do NOT proceed to Phase 5 until you have a single, evidence-backed root cause.

## Phase 5 — Fix the root cause

Apply the minimal fix. Examples (NOT exhaustive — derive yours from the diagnosis):

- **Disk full from screenshots:** `rm -rf ~/workspace/efj-mtgc/screenshots/ui` (gitignored, safe)
- **Disk full from uv cache:** `uv cache prune` first; if still tight, `rm -rf ~/.cache/uv` (forces redownload, costs nothing else)
- **Stale test container holding port:** `bash deploy/teardown.sh <instance> --purge`
- **Stale quadlet unit:** `systemctl --user stop mtgc-<instance>; systemctl --user reset-failed mtgc-<instance>`
- **Leftover podman build state:** `podman system prune` (NOT `-a` unless user agrees)
- **Sibling worktree `.venv` rotting:** confirm with user, then `rm -rf ~/workspace/efj-mtgc-issueN/.venv`

**For destructive cleanup beyond gitignored artifacts (deleting volumes, pruning images, removing other people's worktrees, blowing away caches the user might want), CONFIRM with the user first.** Stale UI screenshots in a gitignored dir don't need confirmation. Anything ambiguous does.

After cleanup, verify with `df -h /home` (or whichever metric was the cause) that the system is now in a healthy state. Don't re-run CI on a half-fixed box.

## Phase 6 — Re-run CI and watch it

```bash
gh run rerun <run-id>
```

Then wait and check:

```bash
gh run view <run-id>            # status check
gh run watch <run-id>           # blocks until done (preferred if not too long)
```

If it fails again, **do not declare victory or call it a flake**. Return to Phase 2 with the new failure log. Iterate until CI is actually green.

## Phase 7 — Prevent recurrence

If the root cause was accumulated state (screenshots, caches, containers), think about whether the workflow that creates that state should clean up after itself. Options:
- Add cleanup to `deploy/teardown.sh`
- Add a cleanup step to the relevant skill (e.g. `qa-finish`, `run-tests`)
- Add a `.gitignore` entry if a new artifact path was missed
- Mention it to the user as a known accumulation point so they can decide

Don't silently make a fix and walk away. If this can happen again, surface it.

## Hard rules

1. **Never re-run CI before diagnosing.** Diagnose, fix, then re-run.
2. **Never use the word "flake"** to describe a failure on this runner. The runner is local; the cause is local.
3. **Never stop at "the network timed out" / "podman crashed".** Those are symptoms. Find the cause.
4. **Never delete files outside the gitignored artifact dirs without confirming.** Other worktrees, podman volumes, the prod data volume — all need explicit user OK.
5. **Always quote the actual failing log line** in your report to the user, so they can verify your diagnosis.
6. **Always verify the fix worked** by checking system state (df, free, ps, etc.) before re-triggering CI.
7. **If you're stuck after a real diagnosis attempt, ask the user.** Don't guess and don't stall.

## Reporting back

When done, tell the user:
- Which run failed and at which step
- The exact log line that revealed the cause
- The root cause (one sentence)
- What you cleaned up / changed
- Resulting system state (e.g. "disk now 9.4G free, was 1.8G")
- Whether the re-run is in flight or already green
- Any prevention notes
