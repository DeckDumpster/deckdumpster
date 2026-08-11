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
| `MTGC_TLS_CERT` / `MTGC_TLS_KEY` | `~/.config/mtgc/<instance>.env` | Container-side paths to the certificate and private key. Both set → the app serves them on 8081. Neither set → today's self-signed behaviour. |

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

## Scripts

| Script | Purpose |
|---|---|
| `seed.sh [--force]` | Create reusable seed data volume. Run once, all future `--init` clones from it |
| `setup.sh <name> [port] [--init] [--test] [--http-port <p>] [--tls-certs <dir>]` | Create instance. `--test` uses pre-built fixture (fast, no network). `--init` clones seed volume. Port auto-assigned if omitted. `--http-port` adds a loopback-only plaintext publish — see [Cloudflare Tunnel origin](#cloudflare-tunnel-origin). `--tls-certs` mounts a host cert directory read-only at `/certs` — see [Trusted certificates](#trusted-certificates) |
| `render-quadlet.sh <name> <port-mapping> <http-port> <tls-certs> [template]` | Render the Quadlet unit to stdout. Called by `setup.sh`; standalone for testing |
| `deploy.sh <name>` | Rebuild image and restart one instance. Regenerates the Quadlet via `setup.sh` if it has gone missing — `--http-port` / `--tls-certs` are re-applied from the env file, so the unit is reproduced rather than downgraded |
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
