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

## Cloudflare Tunnel origin

A tunnel connector (`cloudflared`) runs on the host and reaches the container over loopback. TLS on that hop protects nothing — it is `127.0.0.1` — and terminating it with the auto-generated self-signed cert forces the tunnel route to carry `noTLSVerify: true` permanently. The instance can instead serve the connector over **plain HTTP on a second listener**, while direct-LAN clients keep hitting HTTPS on 8081 exactly as before. One instance, two access paths.

It is off unless you turn it on, and turning it on takes **two independent switches**:

| Switch | Where | Effect |
|---|---|---|
| `MTGC_HTTP_PORT=8080` | `~/.config/mtgc/<instance>.env` | The app binds a second, plain-HTTP listener on that **container** port, in addition to the TLS listener on 8081. Unset → one listener, exactly today's behaviour. A non-integer value fails the server at startup — there is no fallback. |
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

### Why the publish is loopback-only

`127.0.0.1` is hardcoded in `deploy/render-quadlet.sh` and is **not** operator-supplied; `--http-port` takes a port number and is rejected unless it is numeric, so it can never carry an address. This is the safety property the whole arrangement rests on, not an implementation detail: a `0.0.0.0` publish would put an unencrypted copy of the app in front of the LAN, WireGuard, and anything else routed to this host. Binding to loopback means the plaintext listener is reachable by a host-local origin such as `cloudflared` **and by nothing else** — enforced by the publish binding rather than by anyone remembering a rule.

The HTTPS listener on 8081 is untouched by all of this. Direct-LAN access stays HTTPS forever.

### Rollback

Remove `MTGC_HTTP_PORT` from `~/.config/mtgc/<instance>.env` and restart:

```bash
sed -i '/^MTGC_HTTP_PORT=/d' ~/.config/mtgc/<name>.env
systemctl --user restart mtgc-<name>
```

The app is back to a single TLS listener. No rebuild, no data migration. To also drop the host publish, re-run `setup.sh` without `--http-port` and `systemctl --user daemon-reload`. If the tunnel route was switched to plain HTTP, point it back at `https://localhost:8081` with `noTLSVerify: true`.

## Scripts

| Script | Purpose |
|---|---|
| `seed.sh [--force]` | Create reusable seed data volume. Run once, all future `--init` clones from it |
| `setup.sh <name> [port] [--init] [--test] [--http-port <p>]` | Create instance. `--test` uses pre-built fixture (fast, no network). `--init` clones seed volume. Port auto-assigned if omitted. `--http-port` adds a loopback-only plaintext publish — see [Cloudflare Tunnel origin](#cloudflare-tunnel-origin) |
| `render-quadlet.sh <name> <port-mapping> <http-port> [template]` | Render the Quadlet unit to stdout. Called by `setup.sh`; standalone for testing |
| `deploy.sh <name>` | Rebuild image and restart one instance |
| `teardown.sh <name> [--purge]` | Stop and remove instance. `--purge` deletes data volume and env file |

## CI

Push to main auto-deploys `prod`. Use workflow_dispatch to deploy other instances by name.

## Troubleshooting

```bash
systemctl --user status mtgc-<name>
journalctl --user -u mtgc-<name> -f
podman exec -it systemd-mtgc-<name> bash
podman volume inspect systemd-mtgc-<name>-data
```
