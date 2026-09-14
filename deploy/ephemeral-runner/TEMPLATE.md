# Proxmox VM template build sheet — ephemeral CI runner

This document describes exactly what the Proxmox VM template must contain so
that every ephemeral runner cloned from it can execute `bash deploy/ci.sh` to
completion without further provisioning. Build the template by hand in a
Proxmox console, validate it with the checklist at the bottom, then convert
it to a template. **Do not register the GitHub Actions runner inside the
template.** Registration is per-token and per-run; a template with a
pre-registered runner clones into N VMs all claiming to be the same agent.

---

## The non-root user with lingering — the part everybody gets wrong

`deploy/ci.sh` exports `XDG_RUNTIME_DIR=/run/user/$(id -u)` and drives
everything downstream as rootless Podman through `systemctl --user`.
`deploy/setup.sh:231` checks `loginctl show-user "$USER" -p Linger` and
prints a warning if lingering is not set; `deploy/setup.sh:106` writes
Quadlet units to `$HOME/.config/containers/systemd/`, which systemd only
picks up inside a live user session.

**What this means for the template:**

1. The runner must run as an ordinary non-root user (call it `runner`).
2. Lingering must be enabled for that user:
   ```bash
   sudo loginctl enable-linger runner
   ```
   Confirm with `loginctl show-user runner -p Linger` → `Linger=yes`.
3. A real user D-Bus session must be present when the runner agent starts.
   The standard way with systemd is `systemctl --user …` from within a
   lingering session, which `XDG_RUNTIME_DIR` must point into correctly.

A root runner, or a user without lingering enabled, fails deep inside
`deploy/setup.sh` with a `systemctl --user` error that looks nothing like
"linger not set." Lingering is the first thing to check when CI fails
before it reaches the image-build step.

---

## Packages and tooling

Install all of these before converting to a template. The rationale for each
follows; do not trim the list without re-reading the script it came from.

### Podman (rootless-capable)

```bash
sudo apt install -y podman uidmap slirp4netns fuse-overlayfs
```

Rootless Podman requires:
- `uidmap` / `newuidmap` — subordinate UID/GID mapping. Without it,
  `podman run` fails with "newuidmap not found".
- `slirp4netns` or `pasta` — rootless networking. Podman 4.x defaults to
  `pasta` when available; either works. On Debian/Ubuntu: `slirp4netns` is
  the safe choice and is in the default repos.
- `fuse-overlayfs` — rootless overlay storage driver. Without it Podman
  falls back to `vfs` (extremely slow; a ~983 MB builder stage takes
  minutes where overlay takes seconds).

After installing, set up `/etc/subuid` and `/etc/subgid` for the runner user
if they are not already present:
```bash
sudo usermod --add-subuids 100000-165535 --add-subgids 100000-165535 runner
```
Confirm with `podman unshare cat /proc/self/uid_map` as the runner user.

**Minimum Podman version: 4.4.** Quadlet `.container` file support was added
in Podman 4.4. Older versions silently ignore `.container` files —
`systemctl --user start mtgc-<instance>` succeeds but starts nothing, and
every subsequent `podman port` call returns empty. On Ubuntu 22.04 the repo
version is 3.4; install from the Kubic OBS repo or the
`ppa:projectatomic/ppa` PPA to get ≥ 4.4.

**Minimum systemd version: 239.** User-mode systemd generators (the
mechanism Quadlet uses) were introduced in systemd 239. Ubuntu 22.04 ships
systemd 249 (fine); Ubuntu 20.04 ships 245 (fine). Confirm with
`systemctl --version`.

### uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

`deploy/ci.sh` calls `uv sync` and `uv run pytest …` without installing uv
itself. Install as the runner user so `~/.local/bin/uv` is on `PATH`.
Confirm with `uv --version`.

### Playwright / Chromium system libraries

`deploy/ci.sh` runs:
```bash
uv run shot-scraper install
```
This downloads the Chromium binary but **not** its shared-library
dependencies. Those must be present in the OS image. Install them before
baking the template:

```bash
sudo apt install -y \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libasound2 libpango-1.0-0 libpangocairo-1.0-0
```

Without these, `shot-scraper install` succeeds but the first Playwright
launch fails with `error while loading shared libraries: libnss3.so`.
That failure happens mid-suite, long after everything looks fine.

### git, curl, jq

```bash
sudo apt install -y git curl jq
```

`deploy/ci.sh` and several deploy scripts call `curl` and `jq` directly.
`git` is required by the GitHub Actions runner and for `uv` operations that
inspect the repo.

### qemu-guest-agent — enable and start it

```bash
sudo apt install -y qemu-guest-agent
sudo systemctl enable --now qemu-guest-agent
```

The Proxmox `provision.sh` script that clones a template into an ephemeral
VM and prepares it for a run waits for the guest agent to respond before
proceeding. A template without the agent enabled makes every provisioning
call time out. **Enable and start it inside the template — not just install
it — so the service comes up on every clone without further configuration.**

Confirm with `systemctl is-active qemu-guest-agent` → `active`.

### GitHub Actions runner — unpack, do not register

Download the runner tarball and unpack it for the runner user. **Stop
before `./config.sh`.** Registration binds to a token that expires and to a
runner name that must be unique; a pre-registered template clones into N
runners all presenting the same identity, and GitHub refuses all but the
first.

```bash
mkdir -p /opt/actions-runner
cd /opt/actions-runner
# Replace <VERSION> with the latest from github.com/actions/runner/releases
curl -LO https://github.com/actions/runner/releases/download/v<VERSION>/actions-runner-linux-x64-<VERSION>.tar.gz
tar xzf ./actions-runner-linux-x64-<VERSION>.tar.gz
chown -R runner:runner /opt/actions-runner
```

Registration (`./config.sh --url … --token …`) happens inside `provision.sh`
at runtime, using a fresh token fetched for each ephemeral VM.

---

## Disk size

`deploy/ci.sh` calls `deploy/diskcheck.sh --floor` before any build work.
The default floor is `MTGC_DISK_FLOOR_GB=10`, and the check fails the run
rather than letting it proceed to a silent mid-build crash.

On top of that floor, a full CI run writes:

| What                                             | Approximate size |
|--------------------------------------------------|-----------------|
| OS (Debian/Ubuntu minimal)                       | 5 GB            |
| GitHub Actions runner                            | 1 GB            |
| Python packages (`uv sync` + dev deps)           | 2 GB            |
| `uv` cache (`~/.cache/uv`)                       | 1 GB            |
| Playwright / Chromium browser                    | 500 MB          |
| Container image builds — builder stage (×2)      | 2 GB            |
| Container image builds — runtime stage (×2)      | 1.5 GB          |
| Test data volume + WAL                           | 500 MB          |
| Podman image/layer bookkeeping                   | 500 MB          |
| Mandatory headroom floor                         | 10 GB           |
| **Total**                                        | **~24 GB**      |

The factor-of-two on image builds is because `deploy/store-isolation-gate.sh`
runs a **complete** `deploy/setup.sh --test` (including a full image build)
into a probe store before the real CI run does the same into the default
store. Both builds run before the isolation gate tears its probe store down.

The builder stage alone is ~983 MB (noted in `deploy/store-isolation-gate.sh`).
`--full 0` in Proxmox creates a **linked clone**, so the clone is thin at
creation time but the guest still sees — and can fill — the template's full
disk. Set the template disk to **40 GB** to leave comfortable headroom for
concurrent runs, image-layer accumulation, and the 10 GB mandatory floor.

---

## Container store — what to configure (and what the isolation gate needs)

`deploy/ci.sh` sources `deploy/store-lib.sh` and calls
`mtgc_store_load_config`, which reads `~/.config/mtgc/store.env`. On the
shared deployment box, `MTGC_STORE_ROOT` redirects non-prod container builds
off the disk prod runs from. **On a single-tenant ephemeral VM there is no
prod to protect**, so leaving `store.env` unconfigured is correct — the
default Podman store under `$HOME` is the only store, and CI writes to it.

**Does `deploy/store-isolation-gate.sh` pass without `store.env`?**

Yes. When `MTGC_STORE_ROOT` is unset and `store.env` is absent, the gate
selects `${TMPDIR:-/tmp}/mtgc-store-gate-$$` as its probe store. It passes
the probe path explicitly to `deploy/setup.sh` via `MTGC_STORE_ROOT="$PROBE"`,
so `setup.sh` writes the generated Quadlet's `GlobalArgs=` to point at that
probe directory. The gate's positive assertions confirm:
- the Quadlet names the probe store (not the default store),
- the image exists in the probe store, and
- the probe store grew by at least 256 MB.

The gate's negative assertions confirm nothing landed in
`$HOME/.local/share/containers` (the default store under test).

If probe and default store share the same filesystem (common on a VM with one
disk), the gate prints a note but does **not** fail — it proves the stores
are separate *directories*, which is sufficient on a single-tenant machine
where the only concern is correctness, not disk isolation.

**Do not create `store.env` in the template.** A template with a pre-baked
`MTGC_STORE_ROOT` pointing at a path that doesn't exist on the clone's disk
will break `setup.sh` with a path validation error the moment a runner starts.

---

## Networking

The ephemeral VM needs outbound internet access only:
- **GitHub** (`github.com`, `api.github.com`, `*.actions.githubusercontent.com`)
  for the runner agent, checking out code, and downloading release tarballs.
- **Container registries** (`ghcr.io`, `registry-1.docker.io`) for base
  images (`python:3.12-slim`, `ghcr.io/astral-sh/uv:latest`).
- **PyPI / uv** for `uv sync` and `uv run shot-scraper install`.

The Proxmox hypervisor's guest agent channel is used by `provision.sh` to
reach the VM; that works over the hypervisor bus, not the network, so no
Tailscale or tailnet membership is required for the guest. **Leave Tailscale
out of the template.** Every ephemeral device that joins the tailnet must be
cleaned up, and these VMs are created and destroyed automatically.

If your Proxmox host is already on the tailnet and the VM is on a Proxmox
bridge with NAT, the VM gets outbound internet through the host's NAT — no
additional configuration needed. Confirm with `curl -s https://github.com`
from inside the template before converting it.

---

## Verification checklist

Run every step inside the template VM **as the `runner` user**, before
converting it to a template. Each step proves the thing the next one depends
on. The last step is the real workload — a template validated by "packages
installed without error" is a template that fails on its first real CI run.

```bash
# 1. Linger is on
loginctl show-user runner -p Linger | grep -q 'Linger=yes' \
    && echo "PASS: linger" \
    || echo "FAIL: run sudo loginctl enable-linger runner"

# 2. XDG_RUNTIME_DIR exists and the user session is alive
ls /run/user/$(id -u) \
    && echo "PASS: runtime dir" \
    || echo "FAIL: /run/user/$(id -u) missing — log in or start a session"

# 3. Podman version is ≥ 4.4 (Quadlet support)
podman version --format '{{.Version}}' | awk -F. '$1>4 || ($1==4 && $2>=4) { print "PASS: podman", $0; exit } { print "FAIL: podman", $0, "— need >= 4.4" }'

# 4. Rootless networking works
podman run --rm docker.io/library/alpine echo "PASS: rootless container" \
    || echo "FAIL: rootless Podman — check slirp4netns/pasta and subuid mapping"

# 5. fuse-overlayfs is the storage driver (not vfs)
podman info --format '{{.Store.GraphDriverName}}' | grep -qE 'overlay' \
    && echo "PASS: overlay storage driver" \
    || echo "FAIL: not using overlay — check fuse-overlayfs install"

# 6. systemd user session picks up Quadlet (.container files)
mkdir -p ~/.config/containers/systemd
cat > ~/.config/containers/systemd/probe.container <<'EOF'
[Container]
Image=docker.io/library/alpine
Exec=sleep 10
EOF
systemctl --user daemon-reload
systemctl --user is-enabled probe.service >/dev/null 2>&1 \
    && echo "PASS: Quadlet generator active" \
    || echo "FAIL: Quadlet not active — podman < 4.4 or systemd < 239"
rm ~/.config/containers/systemd/probe.container
systemctl --user daemon-reload

# 7. uv is on PATH
uv --version \
    && echo "PASS: uv" \
    || echo "FAIL: uv not found — install with the install script"

# 8. qemu-guest-agent is running
systemctl is-active qemu-guest-agent \
    && echo "PASS: qemu-guest-agent" \
    || echo "FAIL: sudo systemctl enable --now qemu-guest-agent"

# 9. GitHub runner is unpacked (not registered)
ls /opt/actions-runner/run.sh \
    && echo "PASS: runner tarball present" \
    || echo "FAIL: unpack the runner tarball to /opt/actions-runner"
test ! -f /opt/actions-runner/.runner \
    && echo "PASS: runner not pre-registered" \
    || echo "FAIL: runner is registered — re-image from an unregistered copy"

# 10. Outbound internet reaches the registry
curl -sfo /dev/null https://ghcr.io/v2/ \
    && echo "PASS: outbound HTTPS to ghcr.io" \
    || echo "FAIL: no outbound internet — check NAT/bridge"

# 11. The real workload — clone the repo and run deploy/ci.sh end to end.
#     This takes 15–25 minutes. It builds two container images, runs three
#     test tiers (unit, integration, UI), and tears everything down.
#     Use a name that will not collide with any real instance.
cd /tmp
git clone https://github.com/DeckDumpster/mtg-collector repo-ci-tmpl
cd repo-ci-tmpl
INSTANCE=ci-tmpl bash deploy/ci.sh \
    && echo "PASS: full CI run" \
    || echo "FAIL: see output above"
cd /tmp
rm -rf repo-ci-tmpl
```

All steps must pass before you convert the VM to a template. If step 11
fails, do not convert — the clones will fail on the same thing, and the error
will look like a code failure rather than a missing prerequisite.

---

## Converting to a template

After all verification steps pass, in the Proxmox console:

1. Shut the VM down cleanly (`sudo poweroff`).
2. Right-click the VM → **Convert to template**.

Clones created with **Linked Clone** (`--full 0`) share the template's base
disk and are created in seconds. Each clone boots as a fresh VM and
`provision.sh` handles per-run registration before the runner agent starts.
