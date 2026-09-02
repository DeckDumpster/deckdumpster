# MTGC Deployment

Rootless Podman Quadlet deployment. No sudo required (after initial podman install). Each instance is a separate repo clone with its own image, data, and config.

## Prerequisites

### Linux (one-time, needs sudo)

```bash
sudo apt install podman
loginctl enable-linger $USER
```

### macOS (one-time)

```bash
brew install podman
podman machine init
podman machine start
```

The Podman machine (a lightweight Linux VM) persists across reboots but must be started after each reboot with `podman machine start`. Use the `deploy/mac-*.sh` scripts instead of `setup.sh`/`deploy.sh`/`teardown.sh` (no systemd on macOS).

## One-time: set up default env

Create a shared env file so new instances automatically get your API key:

```bash
mkdir -p ~/.config/mtgc
echo "ANTHROPIC_API_KEY=sk-ant-..." > ~/.config/mtgc/default.env
chmod 600 ~/.config/mtgc/default.env
```

## Stable deployment (CD)

Push to main auto-deploys the `prod` instance.

```bash
git clone https://github.com/thaen/efj-mtgc.git /opt/mtgc-prod
cd /opt/mtgc-prod
bash deploy/setup.sh prod 8081
systemctl --user start mtgc-prod
podman exec -it systemd-mtgc-prod mtg setup
```

## Installing timer units

> A feature can land on main, deploy to prod, and still not be running there.

Every scheduled job in this repo is a pair of files — `deploy/<name>.timer` and
`deploy/<name>.service` — rendered per instance into
`~/.config/systemd/user/<name>-<instance>.{timer,service}`. **Both `setup.sh`
and `deploy.sh` install them, every time**, and that is a correction rather
than a convenience: `deploy.sh` only falls back to `setup.sh` when an
instance's Quadlet is *missing*, so for an instance that already exists — prod
— the redeploy path was the sole route a newly added unit could travel, and it
did not travel it. `mtgc-catalog-check` (de-b5q), `mtgc-catalog-refresh`
(de-wdq) and `mtgc-diskcheck` (de-yef) were absent from prod's host entirely,
months after each shipped, with every deploy green (de-46k).

**Installing is not arming, and re-installing does not disarm.** Only unit
files are written; enablement lives in `*.target.wants/` symlinks, which
rewriting a unit file does not touch. So an armed timer stays armed, a disarmed
one stays disarmed, and the install can be unconditional. Which timers an
instance runs stays a decision someone makes once, per instance, by hand — each
job's own section below says how.

Rendering is a pure function of the template, the instance name and the repo
path, so a redeploy against an unchanged checkout rewrites byte-identical
files.

**The unit list is the directory**, read from `deploy/mtgc-*.timer` rather than
written down beside it. A second copy of "which timers exist" is the same bug
one level up: a template added to `deploy/` and forgotten in the list would
install on no host at all, and the only symptom is a timer that never fires. A
`.timer` whose `.service` is missing is a hard error, not a skipped pair.
`teardown.sh` and `prune-instances.sh` read the other end — the units the
**host** has for that instance — because the two lists diverge exactly when a
template is deleted, and then the repo has forgotten a unit the host still has,
armed and firing for an instance that is gone. `prune-instances.sh` had that
bug and the staleness one together: it named four roles, so it left the other
four behind on every orphan it cleaned, and it matched shortest-prefix-first,
so `mtgc-backup-check-<inst>` was reported as an instance called
`check-<inst>`. Mechanism: [`deploy/units-lib.sh`](units-lib.sh); tests in
`tests/test_deploy_units.py`.

```bash
# What is installed for an instance, and what is armed.
systemctl --user list-unit-files "mtgc-*-<instance>.timer"

# What will fire next.
systemctl --user list-timers "mtgc-*-<instance>.timer"
```

## Seed volume (one-time, speeds up all future instances)

Create a reusable seed data volume so `--init` clones it in seconds instead of downloading ~600 MB:

```bash
cd /path/to/efj-mtgc
bash deploy/seed.sh           # ~15-30 min first time
bash deploy/seed.sh --force   # recreate after schema changes
```

## Feature / test instances

Each instance runs from its own checkout on any branch. Port is auto-assigned if omitted.

```bash
git clone https://github.com/thaen/efj-mtgc.git ~/workspace/mtgc-feature-xyz
cd ~/workspace/mtgc-feature-xyz
git checkout feature-xyz

# Fast path: pre-built fixture, no seed volume or network needed (~seconds)
bash deploy/setup.sh feature-xyz --test
systemctl --user start mtgc-feature-xyz

# Full path: clone seed volume (run seed.sh first)
bash deploy/setup.sh feature-xyz --init     # clones seed volume (~seconds)
systemctl --user start mtgc-feature-xyz

# ... develop and test ...

# Clean up when done
bash deploy/teardown.sh feature-xyz         # keeps data volume
bash deploy/teardown.sh feature-xyz --purge  # removes everything
```

## The HTTPS host port is sticky

`setup.sh <name> <port>` pins the host side of the HTTPS publish
(`PublishPort=<port>:8081`); omitting the port renders `PublishPort=:8081` and
Podman picks a free one at container start. **Which of the two an instance is
does not change on its own.** The port given is recorded as `MTGC_PUBLISH_PORT`
in the instance env file and re-applied when omitted, exactly as `--http-port`
and `--tls-certs` are, so the missing-unit path in `deploy.sh` — which re-runs
`setup.sh <name>` with nothing but the name — brings the instance back on the
port it was created on.

Without the record that move was **silent** (de-f2d): `deploy.sh` discovers the
port from `podman port` and health-checks whatever it finds, so a `prod` created
as `setup.sh prod 8081` would come back on a random high port and still report
healthy, while every bookmark, reverse-proxy target, tunnel route and firewall
rule pinned to 8081 broke.

An auto-assigned instance records nothing and keeps floating — auto-assign is the
absence of a port, not a port, and pinning one an instance never asked for would
be the same bug in the other direction. A later explicit port overrides the
record; to hand a pinned instance back to auto-assign, delete the line and
re-render:

```bash
sed -i '/^MTGC_PUBLISH_PORT=/d' ~/.config/mtgc/<name>.env
bash deploy/setup.sh <name>
systemctl --user daemon-reload
```

## Container storage: keeping non-prod off the prod disk

Rootless Podman keeps images, layers and volumes under `$HOME`. On the box that
runs `prod`, `$HOME` is on the 98G LVM root **that `prod` itself runs from** —
34G of the 74G used on `/` was podman's store when this was measured (2026-08-11)
— while the 938G disk holding the checkouts sits nearly empty. So every throwaway
`--test` instance and every CI image build eats the disk prod serves from. `/` has
hit 100% twice, once producing `ld terminated with signal 7 [Bus error]`, which
reads as a toolchain bug and not a disk problem.

**Non-prod storage is opt-in-relocatable; prod's never moves.**

```bash
# Build this instance's image and volume into an alternate store:
MTGC_STORE_ROOT=/big/disk/mtgc-nonprod-store bash deploy/setup.sh scratch --test

# Podman's default store (what prod uses, and the default everywhere else):
bash deploy/setup.sh prod 8081
```

- **Unset is a strict no-op.** With no `MTGC_STORE_ROOT`, the generated Quadlet,
  the timer units and every podman call are exactly what they were before this
  existed. `tests/test_deploy_store.py` asserts that, call by call.
- **Which disk is host config, not a repo constant.** Uncomment
  `MTGC_STORE_ROOT` in `~/.config/mtgc/store.env` — the same directory
  `default.env` and the per-instance env files live in — and every non-prod
  bring-up builds there, CI's and yours. `setup.sh` scaffolds that file
  commented out, so the knob is visible on a new box without changing anything.
  An explicit `MTGC_STORE_ROOT` in the environment wins over the file, and an
  explicit `MTGC_STORE_ROOT=` (empty) is how one run opts back out on a box that
  opts in. The store is never *inferred* from the box's disk layout: a rule like
  "the checkout is on a different filesystem from `$HOME`" describes one machine,
  and on any other it quietly starts a container store at the top of whatever
  external drive or network mount the checkout happens to sit on.
- **`setup.sh` reads `store.env` for every instance except `prod`.** The name is
  the boundary. Originally `setup.sh` did not read the file at all — it is also
  how prod is installed, and where prod's 19 G volume lives is not a host
  config's decision — but that scoped enforcement to the CI path, and the
  documented way to bring an instance up is a by-hand
  `bash deploy/setup.sh <name> --test`, which never goes through CI. So agents
  and humans validating changes, between them the largest non-prod producer of
  container bytes on the box, kept writing them to the disk prod runs from
  unless each one remembered to export the variable (de-oqu). An existing
  instance still keeps the store its unit names, in either direction.
- **The unit is the record.** The generated Quadlet carries a `GlobalArgs=` key
  naming the store, and `deploy.sh`, `teardown.sh`, `restore.sh`, `backup.sh` and
  `prune-instances.sh` read it back — so a bare `bash deploy/teardown.sh <name>`
  removes from the store the instance was *created* in, and a deploy builds into
  the one systemd will look in. An **unstamped** unit says "the default store"
  just as definitely, so an inherited activation is dropped rather than fallen
  through.
- The per-instance price / sealed-catalog / EDHREC timer units carry the same
  flags on their `podman exec` lines, because systemd does not inherit the
  `PATH` shim that scopes the scripts.
- **Two ways into the store, and both stamp the unit.** The documented one is
  `. deploy/store-lib.sh; mtgc_store_load_config; mtgc_store_activate`. The other
  is putting the shim on `PATH` yourself —
  `export PATH="$MTGC_STORE_ROOT/bin:$PATH"` — which is also what an inherited
  activation looks like from a child's side, and is enough on its own to send
  every podman call to the right store. The flags stamped into units are derived
  from `MTGC_STORE_ROOT` rather than read back out of the environment, so neither
  route can produce an unstamped unit. The `PATH`-only one used to: systemd went
  to the *default* store, found no image, and the unit sat in a restart loop
  reporting `pinging container registry localhost: dial tcp 127.0.0.1:443:
  connection refused` — a network error, while the image was in the alternate
  store all along (de-nu5).
- `--root`/`--runroot` per invocation, never a `storage.conf`: the choice cannot
  leak into unrelated podman use on the box.
- **`prod` never sets the variable**, so prod's generated unit is byte-identical
  to the pre-existing one and prod's volumes never move.
- Not covered: `deploy/mac-setup.sh` and friends. On macOS the store lives inside
  the `podman machine` VM, not in the host `$HOME` this is about.

Mechanism and rationale: [`deploy/store-lib.sh`](store-lib.sh).

### The gate that keeps this true

Everything above is a mechanism. What made this a recurring bug is that the rule
around it was a convention — *set this variable, remember that flag* — and
conventions decay without anyone noticing. So CI runs the whole thing for real,
on every PR:

```bash
bash deploy/store-isolation-gate.sh          # ~one image build
```

It brings up a `--test` instance with `MTGC_STORE_ROOT` pointed at a throwaway
probe store, and asserts four things about Podman's **default** store and the
probe: no `mtgc:<instance>` image, `mtgc-<instance>-data` volume or
`systemd-mtgc-<instance>` container in the default store; no image the build
labelled arriving there; no meaningful growth under `~/.local/share/containers`;
*and* that both objects and an image build's worth of bytes are in the probe
store instead. Then it tears both down and re-checks — on both paths, because a
run that just leaked is the run whose cleanup matters most.

The positives are the half that is easy to leave out. A bring-up that silently
did nothing also writes nothing to the default store, so a gate checking only for
the leak would go green on a machine that never built anything.

Names alone would miss a leaked build. `setup.sh` builds `mtgc:latest` before it
tags the instance, and `mtgc:latest` is a name prod's own deploy writes too — so
the tag proves nothing, and the stage commits behind it carry no tag at all.
What every one of them does carry is `cards.dumpster.mtgc.build`, a label the
`Containerfile` applies as the first instruction of each stage (a layer commit
inherits the labels declared before it, not the ones after). The gate enumerates
the default store by that label and ignores anything that was already there at
baseline — `mtgc:prod`, the base image, other instances' images all legitimately
live in it — so only what arrived during the run can fail.

**The one writer the label cannot exclude is our own prod deploy.** It builds the
same `Containerfile` from the same base, so its images carry the same label —
and because podman layers are content-addressed, its layer IDs are not merely
similar to the gate's but *equal*. Nothing measurable separates them.

That was harmless while CI and the deploy shared one runner and one job ran at a
time, which is what the gate assumed. `4c5d9b2` ended it on 2026-08-30 by giving
deploys their own runner on the same box, and at 21:38 that day the gate read
three of a live prod build's layers as a leak, failed a PR on them, and
`podman rmi -f`'d them out from under the running build. The deploy died on the
missing layer and the merge it was carrying never reached prod.

So the gate no longer assumes exclusivity, it takes it: `mtgc_default_store_lock`
(`store-lib.sh`) is held across the whole measurement, and `deploy.sh` takes the
same lock around a build that writes to the default store. Only default-store
writers contend — an instance with a store of its own queues behind nobody — and
CI's jobs are already serialised by having one `rgantt` runner, so in practice
this arbitrates the gate against a prod deploy and nothing else.

If the gate cannot get the lock it does **not** go red: it still runs every
assertion, but reports new MTGC images rather than blaming them on itself, and
reaps nothing. A PR going red because a deploy overlapped it is how a gate's
tolerance gets raised until it stops meaning anything. A deploy that cannot get
the lock does the opposite and fails, because the alternative is building on
layers something else is about to delete.

Walking `podman image history` from the tag, which is what this did first, has a
983 MB blind spot: the `Containerfile` is multi-stage, and the **builder stage**
is a full image that is untagged and is *not* an ancestor of the runtime image,
so it appears in neither. Measured while reproducing de-y5g — a leaked build
left fifteen images in the default store and a history walk accounted for five.

**The gate cleans up what it catches.** The list above is also what its cleanup
removes, so it cannot detect a leak and then leave it on the disk. That used to
be exactly what happened: a failing run `exit 1`'d before its own
leave-nothing-behind check, and the teardown it did run removed only
`mtgc:<instance>` — a *tag*, off an image `mtgc:latest` still held. Measured at
983 MB left on prod's disk per failing run, and `deploy/ci.sh`'s `podman image prune -f`
never collected it because that runs after store selection and is shim-scoped to
the alternate store (de-y5g). A PR that failed the gate repeatedly added about a
gigabyte a run.

**The byte delta is conditional, because `~/.local/share/containers` is not
ours.** On the deployment box it is shared with every other project: prod, the
sibling pokedumpster deployment and its litestream sidecar, that project's
lakehouse pipeline, and any instance nobody relocated. `du` reports bytes and
cannot report a writer. This gate's first CI run went red on 820 MB, none of it
this repo's — a neighbouring prod deploy that built and restarted inside the
gate's four-minute window (de-dk3). So the delta is still measured and still
hard, but only when the default store's inventory of images, containers and
volumes is unchanged across the run, which is the evidence that nobody else was
writing. When something else was, the gate names it and reports the number
instead of asserting it. The checks above do not depend on any of that.

The tolerance is not zero, and that is measured. On the deployment box
(podman 4.9.3, 2026-08-12) one `--test` bring-up moved 1.87 GiB into the probe
store and **24 KB** into `~/.local/share/containers` — podman's user-scope
bookkeeping, chiefly the containers/image blob-info cache, which `--root` does
not relocate. The default ceiling is 64 MiB: far above that bookkeeping, far
below a single image layer. `MTGC_STORE_GATE_TOLERANCE_KB` and
`MTGC_STORE_GATE_FLOOR_KB` override it.

The probe store goes in `MTGC_STORE_GATE_ROOT` if set, else beside the store
`store.env` names (`<store>.gate`), else `$TMPDIR`. Never the configured store
itself — a warm store would make the positive assertions meaningless, and the
teardown would take real instances' images with it.

`tests/test_store_isolation_gate.py` drives the gate against a stubbed podman
told to leak, to leak under a name prod also uses, to spill bytes nothing is
named after, and to build nothing, and checks it goes red every way. The leaking
run is then asked what it left behind: the stub gives each image its own byte
lump, so a test can measure the default store *directory* afterwards rather than
trust the gate's own report of itself, and check that the untagged builder stage
is named on a `FAIL:` line and not merely mentioned. It also
drives one where a *neighbour* writes to the shared store, and checks the gate
goes green — a required check that fails at random is one whose tolerance gets
raised until it stops meaning anything. A gate never observed failing is not
known to work, and one never observed staying green under noise is not known to
be usable.

### What the gate's cleanup may delete

Two separate bounds, and they are separate on purpose.

The first is **who may be writing**: `mtgc_default_store_lock` (store-lib.sh) is
held across the gate's whole measurement, and `deploy/deploy.sh` takes the same
lock around a build into the default store, so an MTGC image that arrives during
the window is the gate's own. That is the attribution, and there is no better
one available — podman layers are content-addressed, so a gate build and a prod
build of the same Containerfile produce the *same* image IDs (see "Deleting a
store" below for what that cost once).

The second is **what may be deleted at all**, and it holds when the first one is
wrong. A lock is only as good as the writers who take it, and `podman build`
typed into a shell takes nothing. So `mtgc_remove_default_store_build_image`
refuses an image that

* any container is built on, running or stopped, or
* wears an `mtgc:` name belonging to an instance that is not this run's.

and removes anything else by untagging its own names and calling `podman rmi`
**without `-f`**. The force flag was the bug, not a detail of it: podman
documents `-f` as *remove all containers that are using the image before
removing the image*, and on 2026-08-30 at 02:12:33 that is precisely what the
gate's cleanup did to prod (de-z9xj). The event log has `systemd-mtgc-prod`
dying and `localhost/mtgc:prod` being untagged in the same second. After that
the name resolved to nothing, so systemd's `Restart=on-failure` asked podman for
it, podman read a missing local name as a *registry* reference, and prod spent
15.5 hours on

```
Error: initializing source docker://localhost/mtgc:prod: pinging container
registry localhost: Get "https://localhost/v2/": dial tcp 127.0.0.1:443:
connection refused
```

No data was lost — `collection.sqlite` and the whole 20 GB volume were untouched
— but the site was down for all of it.

A refusal is printed, not swallowed, and it does **not** turn a red gate green:
MTGC build bytes on the disk prod runs from is still the thing the gate is for.
It only stops the gate proving the point by taking prod out. Up to a gigabyte
left in the default store is the price, and it is the same price the gate
already pays when it cannot take the lock.

### A crash loop has to end

`deploy/mtgc.container` carries `StartLimitIntervalSec=300` / `StartLimitBurst=10`
in `[Unit]`, for every instance including prod. The 15.5-hour outage above was
4195 restart attempts ten seconds apart, and the unit never left `activating` —
there was no failed state for anything to alarm on and no line in the log louder
than the one before it.

systemd's own default limit (5 starts in 10s) cannot fire against `RestartSec=10`:
the attempts are spaced further apart than the window they are counted in, so the
counter empties before it fills. **The interval has to outlast `RestartSec` ×
`StartLimitBurst` or the directive is decoration**, which is what
`tests/test_deploy_quadlet.py` asserts rather than the numbers themselves. Ten
attempts ten seconds apart are spent inside two minutes, and the unit hard-fails.

The boundary that leaves is deliberate. An instance that dies instantly, ten
times running, is a crash loop and stops. One that serves for half a minute
between deaths spaces its attempts past the window and keeps restarting — that is
a flap, not a loop, and the origin serving check is the instrument for it, because
it asks whether the site answers rather than whether the unit is up. There is
deliberately no `OnFailure=` beside the limit: that check already alarms on this
outcome, and a second path to the same page is a second path to keep in sync.
(`mtgc-serving-check-prod` is armed on the deployment box but is not yet in this
repo, which is its own defect — de-u6a2.)

`StartLimitAction` stays at its default, so the unit simply fails and stays
failed. That is the cost, and `deploy/deploy.sh` pays it with a
`systemctl --user reset-failed` before the restart: a redeploy is the fix for
whatever caused the loop, so it is the one path that must not be blocked by it.
By hand, the same:

```bash
systemctl --user reset-failed mtgc-prod
systemctl --user start mtgc-prod
```

### Deleting a store — never `podman system reset`

Everything above teaches you to aim `--root`/`--runroot` at a second store.
`podman system reset` is the one subcommand that ignores them — it resets podman
storage "back to default state", and on 4.9.3 that included `/run/user/$UID/libpod`
and the rootless SHM lock, which no flag pointed at and every store on the box
shares. Run against a throwaway probe store on the sibling project, it took *that*
project's prod down: HTTP 000, podman answering `container state improper` while
the server process was still alive, other instances stuck in state `Created` —
serving but unmanageable. Data survived; the damage was runtime state, repaired
with `systemctl --user restart mtgc-<instance>` per affected instance.

Remove a store with the command that does it correctly:

```bash
bash deploy/store-teardown.sh    # the store store.env names; refuses if there is none
MTGC_STORE_ROOT=/big/disk/mtgc-nonprod-store bash deploy/store-teardown.sh
```

It stops and removes what the store owns *from inside that store*, then `rm -rf`s
the store root and its runroot — a path deletes exactly the path, however podman
resolves things. `teardown.sh` removes an *instance* and leaves the store
standing, because the store is shared by every instance on the box; without this
one accumulates forever. With no alternate store configured it exits non-zero
rather than defaulting to Podman's — that one is prod's. It reports a failure
rather than claiming success when something in the store is still mounted.

`tests/test_deploy_store.py` greps `deploy/` and fails on a `podman system reset`
anywhere in it, so this cannot be reintroduced by hand.

## Cloudflare Tunnel origin

A tunnel connector (`cloudflared`) runs on the host and reaches the container over loopback. TLS on that hop protects nothing — it is `127.0.0.1` — and terminating it with the auto-generated self-signed cert forces the tunnel route to carry `noTLSVerify: true` permanently. The instance can instead serve the connector over **plain HTTP on a second listener**, while direct-LAN clients keep hitting HTTPS on 8081 exactly as before. One instance, two access paths.

It is off unless you turn it on, and turning it on takes **two independent switches**:

| Switch | Where | Effect |
|---|---|---|
| `MTGC_HTTP_PORT=8080` | `~/.config/mtgc/<instance>.env` | The app binds a second, plain-HTTP listener on that **container** port, in addition to the TLS listener on 8081. Unset → one listener, exactly today's behaviour, and a **blank value counts as unset** — `MTGC_HTTP_PORT=` disables the listener rather than crash-looping the instance, the same rule `MTGC_TLS_CERT` / `MTGC_TLS_KEY` read themselves by. A non-empty, non-integer value fails the server at startup — there is no fallback. |
| `bash deploy/setup.sh <name> [port] --http-port <p>` | generated Quadlet unit | Publishes that container port on the **host** as `PublishPort=127.0.0.1:<p>:8080`. Omitted → the line is absent and the unit is byte-identical to a render with no plaintext publish. |

Neither switch does anything useful alone: without the env var nothing is listening on 8080 inside the container; without the flag nothing outside the container namespace can reach it. `8080` is the container-side port the publish targets, so that is the value `MTGC_HTTP_PORT` takes.

```bash
# Enable on an instance. Check the host port is free first — on the CD host
# 8080 and 8082 are already taken by other services; 8091 was picked for prod.
echo "MTGC_HTTP_PORT=8080" >> ~/.config/mtgc/<name>.env
bash deploy/setup.sh <name> <https-port> --http-port 8091
systemctl --user daemon-reload
systemctl --user restart mtgc-<name>

# Verify: plain HTTP answers on loopback, HTTPS still answers, and the plain
# port is NOT reachable from another host on the LAN.
curl -s  -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8091/
curl -ks -o /dev/null -w '%{http_code}\n' https://localhost:<https-port>/
```

Both switches survive a redeploy: `deploy.sh` on an existing instance rebuilds the image and restarts, but does not re-render the Quadlet unit or rewrite the env file. Turning the origin on or off is an env-file edit plus a restart — never a rebuild.

They also survive a **re-render**. `setup.sh` records `--http-port` as `MTGC_HTTP_PUBLISH_PORT` in the instance env file and defaults to the recorded value when the flag is omitted — so the missing-unit path in `deploy.sh` (which re-runs `setup.sh <name>` with no flags) reproduces the publish instead of silently dropping it. That failure would have been quiet: HTTPS keeps answering, so the instance looks healthy while the tunnel origin gets connection refused. An explicit `--http-port` on a later run overrides the record.

### Why the publish is loopback-only

`127.0.0.1` is hardcoded in `deploy/render-quadlet.sh` and is **not** operator-supplied; `--http-port` takes a port number and is rejected unless it is numeric, so it can never carry an address. This is the safety property the whole arrangement rests on, not an implementation detail: a `0.0.0.0` publish would put an unencrypted copy of the app in front of the LAN, WireGuard, and anything else routed to this host. Binding to loopback means the plaintext listener is reachable by a host-local origin such as `cloudflared` **and by nothing else** — enforced by the publish binding rather than by anyone remembering a rule.

The HTTPS listener on 8081 is untouched by all of this. Direct-LAN access stays HTTPS forever.

### Rollback

Remove `MTGC_HTTP_PORT` from `~/.config/mtgc/<instance>.env` and restart:

```bash
sed -i '/^MTGC_HTTP_PORT=/d' ~/.config/mtgc/<name>.env
systemctl --user restart mtgc-<name>
```

Blanking the line (`MTGC_HTTP_PORT=`) does the same thing; deleting it is tidier.

The app is back to a single TLS listener. No rebuild, no data migration. If the tunnel route was switched to plain HTTP, point it back at `https://localhost:8081` with `noTLSVerify: true`.

To also drop the host publish, delete the recorded line and re-render. Omitting `--http-port` is **not** enough — the flag is sticky by design, so that a regenerated unit reproduces the one it replaces:

```bash
sed -i '/^MTGC_HTTP_PUBLISH_PORT=/d' ~/.config/mtgc/<name>.env
bash deploy/setup.sh <name> <https-port>
systemctl --user daemon-reload
```

## Trusted certificates

By default the app generates its own certificate on first start — `server.pem` / `server-key.pem` under `$MTGC_HOME` (`/data` in the container). It is self-signed, and every browser will warn about it.

### Fixing the SAN does not stop the warning

This is the misconception worth stating plainly, because it costs real time: **a browser rejects a self-signed certificate for its issuer, not for its name.** Trust is checked first. If the chain does not terminate in a CA the browser already trusts, the connection is refused before the certificate's `subjectAltName` is ever compared against the address you typed.

So adding your LAN IP to the SAN of the auto-generated certificate, or regenerating it with a better `CN`, changes nothing a user can see. The only two outcomes are:

- **Keep the self-signed certificate** and keep clicking through the warning (or import the certificate into every client's trust store by hand).
- **Get a certificate signed by a public CA** and point the app at it. That is what the rest of this section is about.

The app deliberately implements neither issuance nor renewal. It accepts a certificate pair, reads it once at startup, and does nothing else. Obtaining and renewing is the operator's job.

### Wiring an obtained certificate into an instance

Two switches, same shape as the tunnel origin above: one mounts the files, one tells the app to use them.

| Switch | Where | Effect |
|---|---|---|
| `bash deploy/setup.sh <name> [port] --tls-certs <dir>` | generated Quadlet unit | Mounts the host directory at `/certs` inside the container as `Volume=<dir>:/certs:ro,Z`. `/certs` and `:ro` are hardcoded in `render-quadlet.sh`, not operator-supplied. Omitted → no mount line at all. The directory must already exist, or Podman would create it as an empty root-owned mount point. |
| `MTGC_TLS_CERT` / `MTGC_TLS_KEY` | `~/.config/mtgc/<instance>.env` | Container-side paths to the certificate and private key. Both set → the app serves them on 8081. Neither set → today's self-signed behaviour; a blank value counts as unset, matching `MTGC_HTTP_PORT`. |

Setting exactly one of the pair, or pointing either at something that is not a readable file, **fails the server at startup**. There is no fallback to the self-signed certificate: a deployer who believes they are serving a trusted certificate is never silently downgraded to one that warns.

The two switches have to stay in step, so `--tls-certs` is recorded as `MTGC_TLS_CERTS_DIR` in the same env file and re-applied when the flag is omitted. Without that, a regenerated unit would keep `MTGC_TLS_CERT=/certs/cert.pem` while losing the mount that makes `/certs` exist — an unreadable path, which is exactly the startup failure above, on a loop. Removing the mount means deleting the recorded line (`sed -i '/^MTGC_TLS_CERTS_DIR=/d' ~/.config/mtgc/<name>.env`) along with `MTGC_TLS_CERT` / `MTGC_TLS_KEY`, then re-running `setup.sh`. If the recorded directory has been deleted, `setup.sh` refuses to render rather than quietly producing a unit without the mount.

```bash
mkdir -p ~/.config/mtgc/certs
chmod 700 ~/.config/mtgc/certs
# ... obtain cert.pem / key.pem into it by one of the recipes below ...

cat >> ~/.config/mtgc/<name>.env <<'EOF'
MTGC_TLS_CERT=/certs/cert.pem
MTGC_TLS_KEY=/certs/key.pem
EOF

bash deploy/setup.sh <name> <https-port> --tls-certs ~/.config/mtgc/certs
systemctl --user daemon-reload
systemctl --user restart mtgc-<name>

# Verify: no -k. A trusted certificate means curl validates it unaided.
curl -s -o /dev/null -w '%{http_code}\n' https://<machine>.<tailnet>.ts.net:<https-port>/
journalctl --user -u mtgc-<name> | grep 'externally-provided certificate'
```

`curl` without `-k` succeeding is the whole test. If it fails certificate verification, the browser will too.

**Renewal is yours.** Obtaining and renewing a certificate is the operator's problem — the app only reads the files it is pointed at, once, at startup — and no tool or cadence is recommended here.

### Recipe 1 — `tailscale cert` (recommended)

```bash
sudo tailscale cert \
  --cert-file ~/.config/mtgc/certs/cert.pem \
  --key-file  ~/.config/mtgc/certs/key.pem \
  <machine>.<tailnet>.ts.net
```

That is a genuine Let's Encrypt certificate. Tailscale completes the DNS-01 challenge itself using TXT records under `*.ts.net`, which is why this recipe is short:

- **No domain to buy.** The `ts.net` name your machine already has is the name on the certificate.
- **No DNS API token to store** on the deploy host.
- **No public A record publishing a private IP.** MagicDNS resolves the name inside your tailnet; nothing about your LAN addressing becomes public.

It is also the recipe that survives being handed to someone else. Any deployer runs it on their own tailnet, for their own machine name, with no shared secret and no coordination — which matters, because a colleague deploys his own instance.

If `tailscale cert` refuses to run without root, either keep the `sudo` and `chown` the two files to yourself afterwards (rootless Podman needs to read them as you), or grant yourself LocalAPI access once with `sudo tailscale set --operator=$USER` and drop the `sudo`.

### Recipe 2 — certbot DNS-01 on a domain you own (fallback)

Use this only if the host is not on a tailnet. It works for a LAN host for the same reason Recipe 1 does: the DNS-01 challenge needs only DNS records, never an inbound connection, so nothing has to be reachable on port 80 from the internet.

```bash
certbot certonly --preferred-challenges dns \
  --dns-<your-provider> --dns-<your-provider>-credentials ~/.secrets/dns.ini \
  -d mtgc.example.com
```

The costs it carries and Recipe 1 does not:

- **A DNS API token per deployer**, stored on the deploy host, usually scoped to the whole zone.
- **A public DNS record for an RFC1918 address.** Pointing `mtgc.example.com` at `192.168.1.93` publishes your internal addressing to anyone who resolves the name.
- **A domain to own and pay for**, and a second person deploying their own instance needs either their own domain or a share of yours.

Copy the issued `fullchain.pem` / `privkey.pem` into the mounted directory, readable by the user running Podman.

### Rollback

Remove both variables and restart:

```bash
sed -i '/^MTGC_TLS_CERT=/d;/^MTGC_TLS_KEY=/d' ~/.config/mtgc/<name>.env
systemctl --user restart mtgc-<name>
```

The instance regenerates and serves the self-signed certificate again — browsers warn, `curl -ks` works, nothing else changes. To also drop the mount, re-run `setup.sh` without `--tls-certs` and `systemctl --user daemon-reload`.

## What the nightly backup needs free

> 42 of the 175 nights from 2026-03-05 are missing from the bucket. Every one of
> them was refused for want of free space, and nothing said so.

`backup.sh` stages an uncompressed host-side sqlite snapshot and writes the
tarball beside it, so peak usage is ~1.4x the database — on today's 11.4 GB prod
that is ~15.5 GB, about 15% of the whole 98 GB root volume, and it rises ~91 MB a
day as the database grows ~65 MB a day. That volume also carries prod's own 19 GB
data volume, the retained tarballs and Podman's default store, so any transient
few-GB claim at 03:00 sharp used to cost the night — and a lost night is
permanent: `aws s3 sync` mirrors a directory, so a tarball that was never written
can never be backfilled (de-o4e).

Before refusing, the run reclaims what on that disk is its own (de-4e8):

| Reclaimed | Why it was never a claim on the disk |
|---|---|
| a previous run's staging directory | a run killed mid-snapshot leaves up to a whole database behind, its EXIT trap never fired |
| retained local dailies that S3 already holds | the local copies are a fast-restore convenience; the night is not |

Tarballs go oldest first and the loop stops the moment the run fits, so a roomy
night spends nothing and retention is exactly what it was. One is deleted only
when `aws s3 ls` answers for it **at the same size** — a half-uploaded object
answers too — and nothing local is deleted at all without
`MTGC_BACKUP_S3_BUCKET`, because then the local copy is the only copy. The sync
runs without `--delete`, so reclaiming locally never removes anything from the
bucket.

The image trees are archived straight from the volume mount instead of being
copied into staging first: ~1 GB on prod the run no longer has to have free,
against a budget that only ever set 200 MB aside for them. Reading them live is
no more exposed than the copy was — `cp -a` fails just the same on a file
deleted from under it.

**None of this moves the floor.** The snapshot is a full copy of the database, so
peak usage cannot go below 1x the database however the tarball is written:
SQLite's backup API needs a seekable destination, and neither this box's
`libsqlite3` nor its `sqlite3` shell carries `sqlite_dbpage`, so there is no
streaming a byte-identical copy into a pipe. The bar keeps rising with the
database. The durable fix is to put `MTGC_BACKUP_DIR` on a filesystem that is not
the 98 GB root volume — `/workspaces` is 938 G — which is a host decision about
where prod's backups live, tracked separately.

## Backup freshness check

The nightly backup is a cron job. A cron job can exit 0 having uploaded nothing —
bad credentials, a full disk, an empty tarball, a truncated dump — and log success
every night forever. The bucket already carries the evidence: `gantt-mtgc-backup`
has no object at all for 2026-08-08 or 2026-08-11, and nothing said so.

`backup-check.sh` is the dead-man's switch. It does not ask whether the job ran;
it asks S3 what is actually there, and goes red when:

| Condition | Why it is a failure |
|---|---|
| the bucket cannot be listed | broken credentials or network. "We could not ask" is not "the answer is fine" |
| the prefix is empty | the instance is not backed up |
| newest object older than `MTGC_BACKUP_MAX_AGE_HOURS` (30) | the upload stopped |
| newest object under `MTGC_BACKUP_MIN_BYTES` (1 MiB) | a 0-byte object is not a backup |
| newest object >`MTGC_BACKUP_MAX_SHRINK_PCT`% (10) smaller than the previous one | content went missing; a truncated dump has a plausible mtime and a plausible size |
| `MTGC_BACKUP_S3_BUCKET` unset | nothing off-box to be fresh — a failure, never a skip |

Only when all of those pass does it ping the off-box monitor. The ping lives here
rather than in `backup.sh` because pinging from inside the backup job proves the
job ran, which is the thing already not in question — and because a monitor that
lives off the box also catches a dead box or a timer nobody enabled.

**Nothing in the configuration can turn it into a pass.** An unset
`MTGC_BACKUP_PING_URL` disables the ping and nothing else: freshness is still
verified and a stale backup still exits 1, it just cannot arm the dead-man.

### Arming an instance

`setup.sh` installs `mtgc-backup-check-<instance>.{service,timer}` (6-hourly) and
`mtgc-alert-<instance>@.service`, but enables nothing. To arm one:

```bash
# 1. Pushover credentials for the alert channel (host-wide).
cat > ~/.config/mtgc/alerts.env <<'EOF'
PUSHOVER_TOKEN=CHANGE_ME
PUSHOVER_USER=CHANGE_ME
EOF
chmod 600 ~/.config/mtgc/alerts.env

# 2. A healthchecks.io check with period ~6h and a few hours of grace, so one
#    missed run alerts. Put its ping URL in the instance env file:
#      MTGC_BACKUP_PING_URL=https://hc-ping.com/<uuid>

# 3. Enable the timer.
systemctl --user enable --now mtgc-backup-check-<instance>.timer

# 4. Prove it goes RED before trusting it green — point it at a prefix with no
#    recent object and confirm the failure and the alert:
MTGC_BACKUP_S3_PREFIX=mtgc-<instance>/no-such-prefix/ bash deploy/backup-check.sh <instance>
```

Arming **prod** is Ryan's decision, not an agent's.

### Credentials

The check needs `s3:ListBucket` on the backup bucket and nothing else — verified
by running it under an STS session scoped to exactly that, which passes the check
and still gets 403 on `HeadObject`. Give it read-only credentials: a checker that
could damage what it watches is a liability, and the only AWS call in the script
is `s3api list-objects-v2`.

```json
{ "Effect": "Allow", "Action": "s3:ListBucket", "Resource": "arn:aws:s3:::gantt-mtgc-backup" }
```

## Catalog freshness check

The card catalogue went two months without a new set — the newest set in the
database was Marvel Super Heroes (2026-06-26) while upstream had shipped The
Hobbit on 2026-08-14 — and **every timer on this box was green the whole time**.
Nothing was broken in the sense any of them test for: the price fetch ran, the
sealed catalogue imported, the backup uploaded, `AllPrintings.json` on disk had a
current mtime. Each one answers *did my download succeed*, and each answered yes,
correctly, every day.

`mtg data check-catalog` asks the question none of them does — *is the catalogue
actually current?* — by comparing what we hold against what exists:

```
lag = (newest set released upstream) - (newest set released in our `sets` table)
```

`mtg cache all` upserts **every** Scryfall set unfiltered before it touches a
card, so `sets` is a mirror of Scryfall's `/sets` list. Both sides are drawn from
that one list under one rule, so a current mirror scores exactly **0** — not
"small", 0. There is no release-cadence term to tune around: a quiet month moves
both sides together and the lag stays 0. It leaves 0 only when a set is out in
the world and our copy of the list predates it.

| Condition | Why it is a failure |
|---|---|
| lag > `MTGC_CATALOG_MAX_LAG_DAYS` (7) | a released set has been missing from the catalogue for a week |
| the local database holds no released set at all | the catalogue was never populated |
| Scryfall returns nothing | "we could not ask" is not "the answer is fine" |
| `MTGC_CATALOG_MAX_LAG_DAYS` is not an integer | a typo must not silently restore the shipped default |

Both sides drop sets with `released_at` in the future — Scryfall lists sets weeks
ahead and the ingest stores them then, so a raw `MAX(released_at)` would read the
same far-future set on both sides and measure nothing. That same head start is
why a 7-day threshold is not tight: a catalogue refreshed at any point during a
set's preview season already holds the row and scores 0 on release day, so a
nonzero lag means the mirror predates the set's very appearance upstream.

It deliberately does **not** require the newest set's *cards* to be cached.
`mtg cache all` skips every card with no `oracle_id`, so a token-only or art-series
release (`thob`, `amsh`) stores zero printings by design and that rule would hold
the alarm red forever with nothing able to clear it. An alarm that cannot be
cleared is an alarm that gets ignored.

The verdict travels on the unit's own exit status — STALE exits 1, which fails
`mtgc-catalog-check-<instance>.service`, which fires `OnFailure=` into the shared
Pushover alert. There is no second alerting path to keep in sync, and the same
line covers a stopped container or an unreachable Scryfall. The check reads the
database and Scryfall and writes nothing.

It reads the catalogue through `get_connection()` rather than opening the instance
file: `sets` is in `SHARED_TABLES`, so an instance with `MTGC_SHARED_DB` has an
empty `sets` of its own and reads the real one through a temp view over the
ATTACHed `shared.sqlite`. Every `--test` and `--init` bring-up on a box with the
`mtgc-shared-ref` volume is in that mode, and opening the instance file directly
reports a catalogue with no sets in it — a permanent red no refresh could clear.

### Arming an instance

`setup.sh` installs `mtgc-catalog-check-<instance>.{service,timer}` (daily at
09:00) but enables nothing.

```bash
# 1. Pushover credentials, if not already set — same channel as the backup check.
#    See "Arming an instance" under Backup freshness check.

# 2. Enable the timer.
systemctl --user enable --now mtgc-catalog-check-<instance>.timer

# 3. Prove it goes RED before trusting it green. A current catalogue scores a lag
#    of exactly 0, so -1 is the threshold nothing can pass — run it and confirm
#    both the non-zero exit and the alert. (-e, because podman exec does not pass
#    the host's environment into the container.)
podman exec -e MTGC_CATALOG_MAX_LAG_DAYS=-1 systemd-mtgc-<instance> mtg data check-catalog
```

`mtgc-catalog-refresh` (below) is what clears this alarm; the check grades it,
and its 09:00 slot is after the 01:00 refresh for that reason. On a box where the
refresh timer was never enabled, this check goes red as soon as a set ships. That
is the correct reading, not a false positive.

## Catalog refresh

The other half of the same story. The freshness check tells you the catalogue has
fallen behind; this is the thing that stops it happening. Until it existed
**nothing on a timer refreshed the card catalogue at all** — `mtg cache all` and
`mtg data fetch` were both by hand, both had to be remembered, and for two months
neither was.

```
mtg data refresh-catalog
  ├── mtg cache all      Scryfall: every set, then ~112k cards and printings
  └── mtg data fetch     MTGJSON: AllPrintings.json, imported and version-stamped
```

**One command, one process, one exit status**, and that is the design rather than
a convenience. The refresh was already two commands and the second one is the one
that stopped being run; a unit with two `ExecStart=` lines would rebuild exactly
that failure mode inside systemd, where a half-refresh reads as a green unit. The
Scryfall half runs first because `sets` is what `check-catalog` measures, so a run
that only half-lands lands the half the alarm can see.

Neither half is conditional on what is already on disk. Scryfall regenerates its
bulk export daily and MTGJSON rebuilds daily, so "we already have the file" is not
a reason to skip, and a skip is indistinguishable from a run that had nothing to
do. The cost of that is ~1 GB downloaded per night; the cost of the alternative is
measured in months.

Failures alert directly (`OnFailure=` → the shared Pushover channel) rather than
waiting for the freshness check to notice a week later without the reason. The
import in particular now propagates: it used to run inside a `try/except` that
printed a warning, so a download whose import blew up exited 0 with a current file
on disk and a stale database.

### Arming an instance

`mtgc-catalog-refresh-<instance>.{service,timer}` runs daily at 01:00, ahead of
the sealed catalog, EDHREC, the price fetch and the 09:00 freshness check. It
is installed by every `setup.sh` **and every `deploy.sh`** (see [Installing
timer units](#installing-timer-units)) and enabled by neither — arming is a
per-instance decision, made once, here.

```bash
# 0. Confirm the unit is on this host at all. A timer added to the repo after
#    the instance was installed arrives on its next deploy, not before — and
#    `enable` on a unit that is not there fails with "Unit not found".
systemctl --user list-unit-files "mtgc-catalog-refresh-<instance>.timer"

# 1. Enable the timer.
systemctl --user enable --now mtgc-catalog-refresh-<instance>.timer

# 2. Prove it runs, rather than trusting that it is installed. Expect ~1 GB of
#    downloads and the better part of an hour on a full catalogue.
systemctl --user start mtgc-catalog-refresh-<instance>.service
journalctl --user -u mtgc-catalog-refresh-<instance> -f

# 3. Grade the result with the check that watches it. 0 lag, exit 0.
podman exec systemd-mtgc-<instance> mtg data check-catalog
```

Run it by hand the same way — `podman exec systemd-mtgc-<instance> mtg data
refresh-catalog` — rather than reaching for `mtg cache all` and `mtg data fetch`
separately.

## Low-disk check

> The disk prod serves from has hit 100% twice, and both times the thing that
> silently stopped working was the backup.

/ on the deployment box is 98 G and prod runs from it. It filled on 2026-08-08
and again on 2026-08-11; on both of those nights `mtgc-backup` produced no
object and nothing said so (de-o4e, de-yef). [Container
storage](#container-storage-keeping-non-prod-off-the-prod-disk) bounded the
largest producer of those bytes and CI proves it stays bounded, but prod's own
volume, the price time series, another project on the same box and a stray
tarball are all still on that disk, and none of them announce themselves.

`deploy/diskcheck.sh` has two modes over one threshold source.

```bash
bash deploy/diskcheck.sh                    # ALERT mode: push when a watched fs is full
bash deploy/diskcheck.sh --floor            # GATE mode: exit 1 when a watched fs is short
bash deploy/diskcheck.sh --floor /some/dir  # GATE mode against named paths
```

**Alert mode** is what the timer runs. It compares percent-used against
`MTGC_DISK_THRESHOLD` (default 90) and pushes through the same `alert.sh`
channel as the backup and catalog checks. It is a timer, not a gate: a healthy
disk exits 0. An unconfigured Pushover channel is a failure, not a no-op — a
full disk that reached nobody is the defect this exists to remove. So is a `df`
that cannot answer: measuring no filesystem at all exits 1 rather than passing
quietly, in both modes.

**Gate mode** is what `setup.sh`, `deploy.sh` and CI run before writing gigabytes. It exits
non-zero when a filesystem has less than `MTGC_DISK_FLOOR_GB` free (default 10).
The gate exists because running out mid-build does not fail as a disk error: at
697 MB free a cargo link reported `ld terminated with signal 7 [Bus error]` and
exit 101, which reads as a broken toolchain and cost real diagnosis time. There
is no bypass flag — `MTGC_DISK_FLOOR_GB` is the only knob, and lowering it for
one run is how you push past it deliberately.

Free space is read in 1 K blocks and **truncated**, not from `df -BG`, which
rounds up: 9.2 G free reports as `10G` and would clear a 10 G floor.

### Which filesystems

Two disks matter and they are not the same disk: prod's (`$HOME`, where rootless
Podman keeps prod's 19 G volume) and the non-prod container store
(`MTGC_STORE_ROOT`, on a box that opted in). Both are watched, deduplicated by
mount point, so a box that never opted in checks exactly one filesystem and behaves
as if this paragraph were not here.

`diskcheck.sh` reads `store.env` only to learn a path to *watch*. That is not
the store selection `setup.sh` scopes away from `prod` — nothing here moves a
byte or picks a store, it only decides which `df` lines to look at.

`setup.sh`, `deploy.sh` and CI all gate on the store they have already
resolved, so the floor measures the disk that run will actually write to.
`deploy.sh` adopts the store from the instance's own Quadlet unit, which is how
a prod redeploy measures prod's disk and a non-prod one measures its own.

### Arming an instance

`setup.sh` installs `mtgc-diskcheck-<instance>.{service,timer}` (daily at 22:00,
before the 03:00 backup writes its ~3 GB tarball) but enables nothing. Disk is
host-wide, so enable it on one instance — `prod`.

```bash
# 1. Install the units, if this instance predates the check. setup.sh is the only
#    thing that renders them, and it runs at bring-up — deploy.sh re-renders
#    nothing on its redeploy path, so an instance created before de-yef landed
#    still does not have them however many times it has auto-deployed since
#    (de-wxzx). That is prod's case on the deployment box today, and step 3
#    fails with "Unit not found" rather than arming anything. Check, and if it
#    is not-found, re-run setup.sh for the instance — it is idempotent and
#    enables nothing:
systemctl --user is-enabled mtgc-diskcheck-prod.timer   # not-found => not installed
bash deploy/setup.sh prod

# 2. Pushover credentials, if not already set — same channel as the backup check.
#    See "Arming an instance" under Backup freshness check. An absent
#    ~/.config/mtgc/alerts.env is not a quiet no-op: alert.sh exits 1 and the
#    unit fails, so the first real alert is one nobody was paged for. The
#    already-armed checks are green only because none of them has had to push.

# 3. Enable the timer.
systemctl --user enable --now mtgc-diskcheck-prod.timer

# 4. Prove it goes RED before trusting it green. A threshold of 0 is one nothing
#    can pass — run it and confirm the push actually arrives.
MTGC_DISK_THRESHOLD=0 bash deploy/diskcheck.sh
```

A value passed in the environment beats the file, for every knob below — the
same precedence `store.env` documents for `MTGC_STORE_ROOT`, and what makes the
recipe above work on a box that has already configured a threshold.

Optional, in `~/.config/mtgc/alerts.env`:

```bash
MTGC_DISK_THRESHOLD=90      # percent-used that alerts
MTGC_DISK_FLOOR_GB=10       # gigabytes free below which --floor fails
MTGC_DISK_PATH=/home/you    # the primary filesystem to watch (default $HOME)
```

When it goes red, `deploy/prune-instances.sh` and `podman image prune` are the
first things to reach for. Nothing prunes automatically and nothing should: an
instance holding a volume may be someone's live rig, and deleting it is a
judgement a timer cannot make. The alert exists so a person makes it.

## Memory ceiling on ephemeral instances

> A limit on the CI runner does not reach the containers doing the allocating.

On 2026-08-27 the DeckDumpster CI runner was OOM-killed with roughly ten
polecats in flight. It does not auto-restart, so CI was dead for about 24 hours:
24 PRs queued checks that never ran, `main` froze, and the pipeline looked busy
while landing nothing (de-4u8g).

Hardening the runner unit does not cover this. Every instance is its own
`mtgc-<instance>.service` with its own cgroup, generated from
`deploy/mtgc.container` — a `MemoryMax` on the runner bounds the runner and
nothing it started. So the ceiling goes on the instances:

```ini
[Service]
MemoryMax=2G
```

**Prod is excluded by name**, the same way it is excluded from `store.env`
(see [Container
storage](#container-storage-keeping-non-prod-off-the-prod-disk)) and stated the
same way — *prod never gets a ceiling* — rather than as a guard that could stop
matching. Prod's working set is not something this repo gets to guess at, and an
OOM kill there is an outage rather than a failed test. Prod's generated unit
carries **no** `Memory*` directive at all, not a generous one.

`MemoryMax` and nothing else. It is the bound, and the kernel reclaims page
cache before it OOM-kills, so a `MemoryHigh` beside it would be a second number
to keep in sync that buys throttling rather than a kill — and a CI container
that has gone slow is harder to read than one that has died.

2 G is about 8x measured. A `--test` instance peaked at **257 MB**
(cgroup `memory.peak`) across the whole 158-test integration suite, which is the
heaviest thing CI points at one; it idles around 107 MB. That leaves real
headroom while making concurrent instances additive against a ceiling instead of
against the box's 15 G of RAM. There is **no flag and no env knob**:
the value is a constant in `setup.sh`, so a box that needs a different one edits
it there and every instance picks it up on its next `setup.sh` run. A ceiling
needed only for one run is a `systemctl --user edit mtgc-<name>` drop-in.

The ceiling is derived from the instance name, not recorded in the env file the
way `--http-port` and `--tls-certs` are, so the regeneration `deploy.sh`
performs cannot drop it and there is nothing to go stale.

## CDN deploy check

> A deploy check that does not traverse the CDN is not a deploy check.

On 2026-08-25 six commits deployed and the public site showed none of them for a
day. Everything anyone checked passed: `deploy.sh`'s health check hit
`https://localhost:<port>`, the LAN address served the new pages, the container
was up, the checkout was current. The one hop nobody measured was Cloudflare,
which was holding each document for 24h because the origin said
`public, max-age=86400` with no validator to revalidate against.

`deploy/cdn-check.sh` asks the public URL the same question the health check
asks localhost, and then compares the two:

```bash
bash deploy/cdn-check.sh                                    # defaults below
bash deploy/cdn-check.sh --path /sets                       # any document
bash deploy/cdn-check.sh --url https://magic.dumpster.cards \
                         --origin https://localhost:8081
```

It verifies, in order:

1. the origin answers and carries an ETag;
2. the public URL answers through Cloudflare and carries an ETag;
3. **the two ETags name the same document** — the assertion that would have
   caught it, and the only one that distinguishes "the edge is serving what we
   deployed" from "the edge is serving something, plausibly";
4. the public `Cache-Control` holds the document for under 60s without
   revalidating;
5. a conditional request through the edge returns 304;
6. the edge negotiates gzip;
7. **an asset the document names carries a digest**, and the edge serves it
   `immutable` and byte-identical to the origin. Since de-l23 every `/static`
   reference is rewritten to `/static/<name>.<16 hex>.<ext>`; an origin that
   stopped doing that puts a conditional round trip back on every subresource,
   and an edge holding different bytes for a digest-bearing URL is a cache
   nobody can revalidate out of for a year. A document that names no
   content-addressed asset is itself the finding — this step cannot pass by
   skipping either.

Both sides are asked with `Accept-Encoding: identity`. The server mints a
distinct ETag per encoding on purpose (see `mtg_collector/http_cache.py`), and
Cloudflare re-compresses on its own schedule, so letting either side choose
would make step 3 a coin toss. Cloudflare weakens strong ETags when it
transforms a response, so `W/` is stripped from both sides before comparing;
nothing else is normalised.

**No check may pass by skipping.** There is no flag, no unset variable and no
environment in which this exits 0 without having asked both sides and compared
them.

### Cloudflare Access

`magic.dumpster.cards` is behind Cloudflare Access, so an unauthenticated
request is answered by the Access login page rather than by the app. The script
diagnoses that **by name** instead of letting it surface as an ETag mismatch — a
mismatch would send the reader to the deploy and the cache, neither of which
would be wrong. Give it a service token to get past it:

```bash
export CF_ACCESS_CLIENT_ID=...
export CF_ACCESS_CLIENT_SECRET=...
bash deploy/cdn-check.sh
```

`deploy.yml` runs this as a `cdn-check` job after the prod deploy, reading the
token from the `CF_ACCESS_CLIENT_ID` / `CF_ACCESS_CLIENT_SECRET` repository
secrets. Without them the job fails, reporting the Access wall. That failure is
correct — an unverifiable deploy is exactly the condition the job exists to end
— but it is a one-time configuration, not a code problem.

`tests/test_cdn_check.py` drives the script into each failure it claims to
catch, with a `curl` PATH shim, so none of the above is only ever seen green.

## Scripts

| Script | Purpose |
|---|---|
| `seed.sh [--force]` | Create reusable seed data volume. Run once, all future `--init` clones from it |
| `setup.sh <name> [port] [--init] [--test] [--http-port <p>] [--tls-certs <dir>]` | Create instance. `--test` uses pre-built fixture (fast, no network). `--init` clones seed volume. Port auto-assigned if omitted. `--http-port` adds a loopback-only plaintext publish — see [Cloudflare Tunnel origin](#cloudflare-tunnel-origin). `--tls-certs` mounts a host cert directory read-only at `/certs` — see [Trusted certificates](#trusted-certificates) |
| `render-quadlet.sh <name> <port-mapping> <http-port> <tls-certs> <memory-max> [template]` | Render the Quadlet unit to stdout. Called by `setup.sh`; standalone for testing. `<memory-max>` renders `MemoryMax=` in `[Service]`; empty for prod — see [Memory ceiling on ephemeral instances](#memory-ceiling-on-ephemeral-instances) |
| `deploy.sh <name>` | Rebuild image and restart one instance. Reinstalls the timer units from the checkout every time — see [Installing timer units](#installing-timer-units). Regenerates the Quadlet via `setup.sh` if it has gone missing — `--http-port` / `--tls-certs` are re-applied from the env file, so the unit is reproduced rather than downgraded |
| `teardown.sh <name> [--purge]` | Stop and remove instance. `--purge` deletes data volume and env file |
| `units-lib.sh` | Sourced — renders this repo's timer units for one instance, and lists the ones a host already has. Used by `setup.sh`, `deploy.sh`, `teardown.sh` and `prune-instances.sh`; see [Installing timer units](#installing-timer-units) |
| `store-lib.sh` | Sourced — resolves which Podman store an instance's image and volume live in (`MTGC_STORE_ROOT`). See [Container storage](#container-storage-keeping-non-prod-off-the-prod-disk) |
| `store-teardown.sh` | Remove an alternate container store outright. Refuses when none is configured; never `podman system reset` |
| `store-isolation-gate.sh [name]` | CI gate — brings up a `--test` instance in a probe store and fails if this instance's objects, or any image its build labelled, turn up in Podman's default store, or if nothing was built. Removes what it catches, on both paths. See [The gate that keeps this true](#the-gate-that-keeps-this-true) |
| `ci.sh` | Everything CI runs, in one script: store selection, the disk floor check, the isolation gate, `uv sync`, a `--test` bring-up and all three pytest tiers. `.github/workflows/ci.yml` calls this and nothing else, so a gate wired in here runs in CI *and* by hand. `INSTANCE` defaults to the runner's `ci-test` — override it for a hand run. See [CI](#ci) |
| `cdn-check.sh [--url U] [--origin U] [--path P]` | Verify the deployed document is what the CDN is actually serving, by comparing edge and origin ETags. Also checks revalidation, gzip, that no document is held for hours, and that a content-addressed asset is immutable and identical on both sides — see [CDN deploy check](#cdn-deploy-check) |
| `backup-check.sh [name]` | Verify the newest S3 backup is recent and plausibly sized, then ping the off-box monitor. Read-only; exits 1 on any doubt — see [Backup freshness check](#backup-freshness-check) |
| `alert.sh "<title>" "<message>"` | Push to Pushover. Shared by `backup-check.sh` and `mtgc-alert-<name>@.service`. Exits 1 if the channel is unconfigured, so a dropped alert cannot pass as sent |
| `mtg data check-catalog` (in-container) | Compare the local set list against Scryfall's and exit 1 if it has fallen behind. Read-only — see [Catalog freshness check](#catalog-freshness-check) |
| `mtg data refresh-catalog` (in-container) | Refresh the whole catalogue — Scryfall cache then MTGJSON — in one process, so a half-refresh cannot exit 0. What clears the check above; see [Catalog refresh](#catalog-refresh) |
| `diskcheck.sh [--floor [path...]]` | Alert when a watched filesystem is over `MTGC_DISK_THRESHOLD`% used; `--floor` instead exits 1 when one has less than `MTGC_DISK_FLOOR_GB` free. Called by `setup.sh`, `deploy.sh` and CI before they write gigabytes — see [Low-disk check](#low-disk-check) |

## CI

`.github/workflows/ci.yml` checks out the repo and runs `bash deploy/ci.sh`. That is its
only step, so **anything not invoked from `deploy/ci.sh` never runs in CI** — a new gate
goes in the script, not the workflow. Keeping the steps inline in YAML meant a red CI could
not be reproduced locally, and left the rig's agent instructions — which live outside this
repo, and so could not be corrected from inside it — pointing at a `deploy/ci.sh` that did
not exist; de-3a0 read that instruction, found no such file and stopped (de-xz8).

Run the whole job by hand with an instance name of your own:

```bash
INSTANCE=ci-<yourname> bash deploy/ci.sh
```

`INSTANCE` defaults to `ci-test`, which is the self-hosted runner's own instance — and the
runner shares a machine with your worktree, so taking the default mid-job tears its
container down. The UI tier drives Claude Vision and needs `ANTHROPIC_API_KEY`; CI passes
it in as a repository secret, and without it that tier fails loudly rather than skipping.

Push to main auto-deploys `prod`. Use workflow_dispatch to deploy other instances by name.

CI builds honour `~/.config/mtgc/store.env`, so on a box that opts in, nothing
the test job builds lands on the disk prod runs from. `deploy.yml` — the workflow
that deploys `prod` — deliberately does not read it.

## Troubleshooting

```bash
systemctl --user status mtgc-<name>
journalctl --user -u mtgc-<name> -f
podman exec -it systemd-mtgc-<name> bash
podman volume inspect systemd-mtgc-<name>-data
```
