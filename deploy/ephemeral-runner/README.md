# Ephemeral CI Runner — Proxmox scripts

Three scripts that a GitHub-hosted runner drives over SSH to clone a Proxmox
VM template into a one-shot Actions runner and destroy it afterwards. They
live here rather than inline in workflow YAML so that every `qm` call can
be exercised by hand and a red CI run can be reproduced locally.

## What each script does

### `provision.sh <runner-label> <repo-url>`

Runs on the Proxmox host. Clones a VM template into a new one-shot runner,
injects the registration token via cloud-init, and starts the VM. The
registration token is read from stdin (one line), not from the command line —
a token on `argv` or in `$SSH_ORIGINAL_COMMAND` lands in sshd logs and in
Proxmox's task journal for the lifetime of the token (~1 h).

1. Reads the registration token from stdin.
2. Picks a VMID with `qm nextid` and retries on collision.
3. Clones the template with `qm clone ... --full 0`.
4. Writes `<VMID> <label> <epoch>` to the ledger file immediately after the
   clone so `reap.sh` can find the VM even if this script is killed before it
   finishes.
5. Prints the VMID on **stdout**.
6. Writes a cloud-init user-data snippet with the token, label, and repo URL
   to Proxmox storage and attaches it to the cloned VM with `qm set --cicustom`.
7. Starts the VM.
8. Polls `qm guest cmd <VMID> ping` until the guest agent answers.

The guest boots, reads the injected data from the cloud-init datasource, and
self-registers via `/home/runner/start-runner.sh`. The registration uses
`--ephemeral` and `--labels <runner-label>`.
Without `--ephemeral` the runner stays registered after its job and the repo
accumulates a permanently-offline runner entry per CI run, which still carries
its labels and causes later jobs targeting those labels to queue against a
runner that no longer exists.

### `teardown.sh <vmid>`

Runs on the Proxmox host. Destroys one runner VM via the Proxmox HTTP API
and removes its ledger line. Designed to run under `if: always()` — exits
zero if the VM is already gone so a cancelled run does not report a spurious
failure.

Five guards prevent destroying the wrong thing, applied in order:

- Empty or non-numeric argument → exit non-zero, API is never called.
- VMID equals `TEMPLATE_VMID` → exit non-zero.
- VM does not exist (API returns 404) → clean up stale ledger line and
  exit 0. This runs **before** the ledger guard so a second teardown call
  (after the first removed the ledger line) exits 0 rather than 1. A
  connection error or auth failure is not treated as "already gone" — those
  propagate as failures so a broken API cannot silently claim success.
- VMID not in the ledger → exit non-zero.
- VM name does not match `gh-runner-<vmid>` (read from the API config JSON,
  not from `qm` output) → exit non-zero.

After stopping, teardown polls the stop task's status and confirms the VM
is stopped before issuing DELETE. A guest that ignores ACPI shutdown is
force-stopped rather than passed straight to a destroy that would be
refused.

### `reap.sh [--max-age-hours N] [--dry-run]`

Runs on the Proxmox host. Destroys every VM named `gh-runner-*` older than N
hours (default 4). `if: always()` does not cover a run that GitHub drops, a
cancellation landing between clone and output, or the hypervisor rebooting
mid-run; without a reaper those become orphan VMs discovered as a
storage-full alert weeks later.

Age is read from the ledger (authoritative) and falls back to the creation
timestamp in `qm config` for a VM whose ledger line was lost — the lost-ledger
case is exactly the one that produces orphans, so falling back rather than
skipping is the correct tradeoff.

`--dry-run` prints what it would destroy and touches nothing. Run it first
whenever the ledger looks suspicious.

## Installation on the Proxmox host

Copy all scripts to the host and make them executable:

```bash
SCRIPTS_DIR=/usr/local/lib/gh-ephemeral-runner
mkdir -p "$SCRIPTS_DIR"
cp provision.sh teardown.sh reap.sh forced-command.sh "$SCRIPTS_DIR/"
chmod 755 "$SCRIPTS_DIR/"*.sh
```

Create the ledger directory:

```bash
mkdir -p /var/lib/gh-ephemeral-runner
```

### SSH keypair for the GitHub-hosted runner

The GitHub Actions workflow SSHes to the Proxmox host as the `gh-runner`
non-root user (see "Proxmox user permissions" below) to call these scripts.
Generate a keypair:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/gh-runner-invoke -C "gh-actions-ephemeral-runner"
```

Add the public key to `~gh-runner/.ssh/authorized_keys` on the Proxmox host.
Pin it to `forced-command.sh` with `restrict` plus an explicit `no-pty`:

```
command="/usr/local/lib/gh-ephemeral-runner/forced-command.sh",restrict,no-pty ssh-ed25519 AAAA... gh-actions-ephemeral-runner
```

`restrict` implies no-port-forwarding, no-x11-forwarding, no-agent-forwarding
and all future forwarding types added to OpenSSH. `no-pty` is stated
explicitly to make the intent clear.

`forced-command.sh` parses `$SSH_ORIGINAL_COMMAND` without eval, validates
the verb and every argument against positive patterns, and dispatches to
`provision.sh`, `teardown.sh`, or `reap.sh` — and to nothing else. The
registration token is passed on stdin and forwarded through unchanged; it
never appears in the SSH command string or in sshd logs.

### VM template requirements

The template VM (default VMID set by `TEMPLATE_VMID`, see below) must have:

- **A cloud-init drive** (`ide2` slot set to `<storage>:cloudinit`). Without it
  there is nowhere for `provision.sh` to inject the registration token. The
  cloud-init drive must be in the template so every clone inherits it
  automatically.
- **`agent: 1` in the Proxmox VM config** (set before sealing with
  `qm set <TEMPLATE_VMID> --agent 1`). This is the host-side half of the QEMU
  guest agent channel; the guest-side half is `qemu-guest-agent` installed and
  running inside the VM. Without this line the channel is never opened and
  `provision.sh`'s readiness poll burns its full `TASK_TIMEOUT` and exits 1.
- QEMU guest agent installed and enabled (`apt install qemu-guest-agent`)
- A `runner` user
- `/home/runner/start-runner.sh` — the guest-side self-registration script
  that `start-runner.service` calls at boot. It reads the injected token and
  label from the cloud-init datasource and calls `config.sh --ephemeral`. See
  `TEMPLATE.md` for the full build step.

## Environment variables

All three scripts read `TEMPLATE_VMID` (default `101`) and `LEDGER_FILE`
(default `/var/lib/gh-ephemeral-runner/active`). The template VMID is never
acted on — it is the thing being cloned.

### `provision.sh`

| Variable | Default | Purpose |
|---|---|---|
| `CLONE_RETRIES` | `5` | Attempts to find a free VMID before giving up |
| `SNIPPETS_DIR` | `/var/lib/vz/snippets` | Where the cloud-init snippet is written. The storage must have the `snippets` content type enabled; the snippet is referenced as `local:snippets/gh-runner-<vmid>.yaml`. |
| `TASK_TIMEOUT` | `120` | Seconds to wait for a Proxmox UPID task to complete |
| `CRED_FILE` | `/etc/gh-ephemeral-runner/token` | File sourced for the API credentials |

### `teardown.sh`

| Variable | Default | Purpose |
|---|---|---|
| `STOP_TIMEOUT` | `60` | Seconds to wait for orderly stop before force-stopping |
| `STOP_POLL_INTERVAL` | `2` | Seconds between stop-task polls |
| `FORCE_STOP_WAIT` | `5` | Seconds to wait after a force-stop |

### `reap.sh`

| Variable | Default | Purpose |
|---|---|---|
| `GITHUB_TOKEN` | *(required for the busy check)* | GitHub API token |
| `GH_REPO` | *(required for the busy check)* | Repository in `owner/repo` form |
| `PVE_API_HOST` | `localhost` | Proxmox API host |
| `PVE_API_PORT` | `8006` | Proxmox API port |

Without `GITHUB_TOKEN` and `GH_REPO`, `reap.sh` runs in a degraded mode: the
busy check is skipped and VM age is the only guard. It says so on stderr.

### Credentials — the three scripts do not agree on the names

This is a defect, recorded here rather than papered over, because a reader who
exports one set and not the other gets a failure that looks exactly like a dead
API. The three scripts landed from separate beads and each named the same
Proxmox API credential differently. Until that is reconciled, **export all of
them**:

| Variable | Read by |
|---|---|
| `PVE_NODE` | `provision.sh`, `teardown.sh`, `reap.sh` |
| `PVE_TOKEN_ID` / `PVE_TOKEN_SECRET` | `provision.sh`, `reap.sh` |
| `PVE_API_TOKEN_ID` / `PVE_API_TOKEN_SECRET` | `teardown.sh` — the same token, different name |
| `PVE_HOST` | `teardown.sh` |
| `PVE_API_HOST` / `PVE_API_PORT` | `reap.sh` |

`provision.sh` sources `$CRED_FILE` before checking; `teardown.sh` and
`reap.sh` read the ambient environment only. A credential file written for one
will leave the others unset, and `curl` reports an unset credential and a dead
API identically.

Set these in the environment the scripts run in. On a Proxmox host running the
scripts directly, export them in the shell or in a file the calling service
sources. In the GitHub Actions workflow that reaches the host, pass them
through the dispatcher's environment; the exact mechanism is the companion
workflow bead's concern.

## Ledger file

`/var/lib/gh-ephemeral-runner/active` (overridable via `LEDGER_FILE`) holds
one record per live runner VM:

```
<VMID> <runner-label> <unix-epoch>
```

`provision.sh` appends a line immediately after `qm clone` succeeds.
`teardown.sh` and `reap.sh` delete the line after `qm destroy` succeeds.

The ledger is the link between a VMID and the CI run that provisioned it. It
is also what `teardown.sh`'s guard checks — a VMID absent from the ledger is
refused, so a mistyped id or an injected argument cannot destroy an unrelated
VM.

## Scheduled reaper

Two paths run the reaper, and both are required.

**.github/workflows/reap-runners.yml** runs hourly on a GitHub-hosted runner,
connects to the hypervisor over Tailscale + SSH, and **exits non-zero when it
destroys anything** — making a failed teardown visible as a red workflow run.
Use `workflow_dispatch` (dry_run defaults to true) to inspect the ledger without
touching anything.

**A host cron** is the belt-and-braces path for when GitHub Actions itself is
unavailable. That is precisely the condition most likely to drop a run
mid-provision: if the Actions platform goes down between `provision.sh` finishing
and `teardown.sh` running, no `workflow_dispatch` fires, no `if: always()` step
runs, and the VM sits until the cron clears it.

Install a cron job on the Proxmox host to run `reap.sh` every hour:

```
# /etc/cron.d/gh-runner-reap  — destroy orphan ephemeral runner VMs
0 * * * * root TEMPLATE_VMID=101 /usr/local/lib/gh-ephemeral-runner/reap.sh --max-age-hours 4
```

Adjust `TEMPLATE_VMID` if your template lives at a different id.

The cron cleans up silently; the workflow makes the finding visible. Both paths
call the same `reap.sh` with the same `--max-age-hours 4` argument so neither
races a live build.

## Proxmox user permissions

All three scripts use the Proxmox HTTP API with an API token. None of them
shell out to `qm`: `qm` talks to pmxcfs over `/run/pve-cluster/cfs.sock`,
which is gated against non-root users, so a non-root caller gets
`ipcc_send_rec failed` and `Unable to load access control list` on every
command. An API token needs no OS privileges and keeps the `pveum` ACL as a
real enforcement layer — a hole in the dispatcher still cannot reach a VM
outside the pool.

Create the role, pool, user and token on the Proxmox host as root. This
privilege list was verified against `pveum role list` on a PVE 9 host; do not
copy an older list, several entries below are load-bearing:

```bash
pveum role add GHRunner --privs \
    "VM.Allocate,VM.Audit,VM.Clone,VM.Config.CPU,VM.Config.Disk,\
VM.Config.Memory,VM.Config.Network,VM.Config.Options,\
VM.GuestAgent.Audit,VM.PowerMgmt,\
Datastore.AllocateSpace,Datastore.Audit,\
Pool.Audit,Pool.Allocate"

pveum pool add ephemeral-ci
pveum user add gh-runner@pam
pveum user token add gh-runner@pam ephemeral --privsep 1

# Grant the user AND the token. With --privsep 1 a token carries only the
# privileges granted to the token itself, so both sets of grants are required.
for who in "--user gh-runner@pam" "--tokens gh-runner@pam!ephemeral"; do
    pveum acl modify /pool/ephemeral-ci             $who --role GHRunner
    pveum acl modify /storage/local-lvm             $who --role GHRunner
    pveum acl modify /sdn/zones/localnetwork/vmbr0  $who --role PVESDNUser
done

pveum pool modify ephemeral-ci --vms 101   # the template must be in the pool
```

The token secret is printed once by `pveum user token add` and is not
retrievable afterwards.

Four notes on that privilege list:

- `VM.Allocate` creates and destroys a VMID. Without it the clone fails.
- `VM.GuestAgent.Audit` covers the `ping` and `network-get-interfaces` agent
  calls. It does not grant guest command execution, which is correct — nothing
  here needs it.
- `Pool.Allocate` is required because cloning with `--pool` changes pool
  membership. Granted at `/pool/ephemeral-ci` it reaches that pool and no other.
- There is deliberately no `VM.Monitor`. It gates the QEMU monitor, which none
  of these scripts touch, and it is not a valid privilege on current PVE —
  `pveum role add` rejects the entire command with
  `invalid format - invalid privilege 'VM.Monitor'`.

The bridge grant on `/sdn/zones/localnetwork/vmbr0` is **required, not
optional**. PVE 8.2+ gates bridge attachment; without it the clone fails with
HTTP 403 and `Permission check failed (/sdn/zones/localnetwork/vmbr0,
SDN.Use)`. Replace `local-lvm` with whatever storage the template's disk
actually lives on — check with
`qm config 101 | grep -E '^(scsi|virtio|sata)0:'`.

Scoping to `/pool/ephemeral-ci` means the token can only see the template and
live clones; other VMs on the host are unreachable even if the token leaks.
