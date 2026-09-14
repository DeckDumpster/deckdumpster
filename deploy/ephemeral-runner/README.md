# Ephemeral CI Runner — Proxmox scripts

Three scripts that a GitHub-hosted runner drives over SSH to clone a Proxmox
VM template into a one-shot Actions runner and destroy it afterwards. They
live here rather than inline in workflow YAML so that every `qm` call can
be exercised by hand and a red CI run can be reproduced locally.

## What each script does

### `provision.sh <runner-label> <repo-url>`

Runs on the Proxmox host. Clones a VM template into a new one-shot runner,
starts it, waits for the QEMU guest agent to answer, then registers the
runner over SSH. The registration token is read from stdin (one line), not
from the command line — a token on `argv` or in `$SSH_ORIGINAL_COMMAND` lands
in sshd logs and in Proxmox's task journal for the lifetime of the token (~1 h).

1. Reads the registration token from stdin.
2. Picks a VMID with `qm nextid` and retries on collision.
3. Clones the template with `qm clone ... --full 0`.
4. Writes `<VMID> <label> <epoch>` to the ledger file immediately after the
   clone so `reap.sh` can find the VM even if this script is killed before it
   finishes.
5. Prints the VMID on **stdout** and starts the VM.
6. Polls `qm guest cmd <VMID> ping` until the guest agent answers.
7. Discovers the guest's IP from `qm guest cmd <VMID> network-get-interfaces`.
8. SSHes to the guest and invokes `/usr/local/bin/register-runner <label>`,
   passing the token and repo URL via stdin rather than on the command line.

The registration call uses `--ephemeral` and `--labels <runner-label>`.
Without `--ephemeral` the runner stays registered after its job and the repo
accumulates a permanently-offline runner entry per CI run, which still carries
its labels and causes later jobs targeting those labels to queue against a
runner that no longer exists.

### `teardown.sh <vmid>`

Runs on the Proxmox host. Destroys one runner VM and removes its ledger line.
Designed to run under `if: always()` — exits zero if the VM is already gone
so a cancelled run does not report a spurious failure.

Four guards prevent destroying the wrong thing:

- Empty or non-numeric argument → exit non-zero, `qm` is never called.
- VMID equals `TEMPLATE_VMID` → exit non-zero.
- VMID not in the ledger → exit non-zero.
- VM name does not match `gh-runner-<vmid>` (checked with `qm config`, not
  by parsing `qm list` output) → exit non-zero.

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

### SSH keypair inside the runner guest

The guest VM template must have an SSH server and a `runner` user whose
`~/.ssh/authorized_keys` contains the public half of `RUNNER_SSH_KEY`
(default `~/.ssh/gh-runner` on the Proxmox host). `provision.sh` connects
to this key to register the runner.

Generate the keypair on the Proxmox host:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/gh-runner -C "gh-ephemeral-runner-guest"
```

Bake the public key into the template's `~runner/.ssh/authorized_keys` before
sealing it. Do **not** bake a registration token into the template — tokens are
short-lived (~1 h) and a token baked into an image has no expiry or revocation
story.

### VM template requirements

The template VM (default VMID set by `TEMPLATE_VMID`, see below) must have:

- QEMU guest agent installed and enabled (`apt install qemu-guest-agent`)
- SSH server running (`openssh-server`)
- A `runner` user (or whatever `RUNNER_SSH_USER` names)
- `/usr/local/bin/register-runner` executable, which reads the runner label
  from its first positional argument, and the registration token and repo URL
  from stdin (token on the first line, repo URL on the second). It calls the
  GitHub Actions runner's `config.sh --ephemeral --labels <label>
  --unattended --url <repo> --token <token>` and starts the runner service.
  Reading from stdin keeps the token off every process's argument list.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `TEMPLATE_VMID` | `101` | Source VM template VMID |
| `RUNNER_SSH_KEY` | `~/.ssh/gh-runner` | SSH private key for the runner guest |
| `RUNNER_SSH_USER` | `runner` | SSH user inside the runner guest |
| `LEDGER_FILE` | `/var/lib/gh-ephemeral-runner/active` | Active-runner ledger |
| `CLONE_RETRIES` | `5` | Attempts to find a free VMID before giving up |
| `AGENT_TIMEOUT` | `120` | Seconds to wait for the guest agent to answer |

Set these in the environment the scripts run in. On a Proxmox host running
the scripts directly, export them in the shell or in a file the calling
service sources. In the GitHub Actions workflow that SSHes to the host, pass
them through the SSH command's environment or as arguments; the exact
mechanism is the companion workflow bead's concern.

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

Install a cron job on the Proxmox host to run `reap.sh` every hour:

```
# /etc/cron.d/gh-runner-reap  — destroy orphan ephemeral runner VMs
0 * * * * root TEMPLATE_VMID=101 /usr/local/lib/gh-ephemeral-runner/reap.sh --max-age-hours 4
```

Adjust `TEMPLATE_VMID` if your template lives at a different id.

## Proxmox user permissions

The OS user that runs these scripts needs permission to call `qm`. Create a
non-root Proxmox user and a role with the privileges these scripts actually
require:

```bash
pveum role add GHRunner -privs "VM.Allocate VM.Clone VM.Config.Disk VM.Config.Network VM.Config.CPU VM.Config.Memory VM.PowerMgmt VM.Audit VM.Monitor Datastore.AllocateSpace"
pveum user add gh-runner@pam
pveum aclmod / -user gh-runner@pam -role GHRunner
```

`VM.Allocate` is required: `qm nextid` and `qm destroy` both need it to
allocate and release VMIDs. `VM.Clone` covers `qm clone`; `VM.PowerMgmt`
covers `qm start` and `qm stop`; `VM.Config.*` covers setting the VM name at
clone time; `Datastore.AllocateSpace` covers the linked-clone disk allocation.

Grant access only to the pool or resource group the template and clones live
in rather than `/` if your Proxmox setup supports it. Run the three scripts
end-to-end as this user against a real Proxmox node before relying on this
list — a role that has never been exercised is a guess, and `qm` error
messages name the missing privilege when a call is refused.
