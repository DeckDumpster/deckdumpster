#!/usr/bin/env bash
#
# handles.sh -- the multi-tenant front door, against a real container and a real
# JWKS server (multi-tenancy bead 11, sp-0knuwi).
#
# Runs the instance's own image (localhost/mtgc:$INSTANCE, built by setup.sh) in
# multi-tenant mode on a throwaway volume, with Cloudflare Access pointed at
# tests/jwks_server.py on the host loopback (--network=host, so the container's
# 127.0.0.1 is the host's). It asserts:
#
#   * multi mode without Access refuses to start;
#   * a bound email is served (200), an unbound one is 403, a bad, expired or
#     absent token is 401, and /health needs no token;
#   * looking an identity up provisions nothing;
#   * the single-tenant instance this CI run already built is unaffected.
#
# Each refusal has a control arm: the same request with the bound token is 200,
# so a server that refused everything cannot pass.
#
# Usage: INSTANCE=ci-<name> bash deploy/handles.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
cd "$REPO_DIR"

INSTANCE="${INSTANCE:-ci-test}"

# Every podman call below must hit the store the instance's image was built in.
# shellcheck source=deploy/store-lib.sh
. "$SCRIPT_DIR/store-lib.sh"
mtgc_store_adopt_instance "$INSTANCE"
mtgc_store_activate
IMAGE="localhost/mtgc:${INSTANCE}"
PORT="${HANDLES_PORT:-18091}"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/handles.XXXXXX")"
VOLUME="mtgc-handles-$$"
CONTAINER="mtgc-handles-$$"
JWKS_PID=""
BOUND="bound@example.org"
UNBOUND="unbound@example.org"
FAILED=0

cleanup() {
    podman rm -f "$CONTAINER" >/dev/null 2>&1 || true
    podman volume rm -f "$VOLUME" >/dev/null 2>&1 || true
    [ -n "$JWKS_PID" ] && kill "$JWKS_PID" >/dev/null 2>&1 || true
    rm -rf "$WORK"
}
trap cleanup EXIT

fail() { echo "FAIL: $*" >&2; FAILED=1; }
pass() { echo "ok:   $*"; }

podman image exists "$IMAGE" || { echo "no image $IMAGE: run deploy/setup.sh $INSTANCE --test first" >&2; exit 2; }

# --- the JWKS server and the tokens a container can present ---------------------
uv run python tests/jwks_server.py serve "$WORK/jwks" "$BOUND" "$UNBOUND" &
JWKS_PID=$!
for _ in $(seq 1 50); do [ -f "$WORK/jwks/ready" ] && break; sleep 0.2; done
[ -f "$WORK/jwks/ready" ] || { echo "JWKS server did not start" >&2; exit 2; }
JWKS_URL="$(cat "$WORK/jwks/url")"

ACCESS_ENV=(
    -e "MTGC_ACCESS_TEAM_DOMAIN=https://gate.cloudflareaccess.com"
    -e "MTGC_ACCESS_AUD=gate-aud-tag"
    -e "MTGC_ACCESS_JWKS_URL=${JWKS_URL}"
)
BASE=(podman run --rm --network=host -v "${VOLUME}:/data:Z"
      -e MTGC_HOME=/data -e MTGC_DB=/data/collection.sqlite)

podman volume create "$VOLUME" >/dev/null

# --- multi without Access refuses to start --------------------------------------
if out="$("${BASE[@]}" -e MTGC_MULTITENANT=1 -e MTGC_HTTP_PORT="$PORT" "$IMAGE" 2>&1)"; then
    fail "multi-tenant mode without Access started"
elif grep -q "Access is not configured" <<<"$out"; then
    pass "multi mode without Access refuses to start"
else
    fail "multi without Access exited, but not for the right reason: $out"
fi

# --- provision: one tenant bound to one email, the legacy db initialised --------
"${BASE[@]}" --entrypoint python "$IMAGE" -c \
    "import sqlite3; from mtg_collector.db.schema import init_db; c = sqlite3.connect('/data/collection.sqlite'); init_db(c); c.commit()"
"${BASE[@]}" -e MTGC_MULTITENANT=1 --entrypoint mtg "$IMAGE" tenant create alice >/dev/null
"${BASE[@]}" -e MTGC_MULTITENANT=1 --entrypoint mtg "$IMAGE" tenant identity add alice "$BOUND" >/dev/null

podman run -d --name "$CONTAINER" --network=host -v "${VOLUME}:/data:Z" \
    -e MTGC_HOME=/data -e MTGC_DB=/data/collection.sqlite \
    -e MTGC_MULTITENANT=1 -e MTGC_HTTP_PORT="$PORT" "${ACCESS_ENV[@]}" \
    "$IMAGE" >/dev/null

for _ in $(seq 1 60); do
    curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1 && break
    sleep 1
done
curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1 || {
    echo "multi-tenant server did not come up" >&2
    podman logs --tail 60 "$CONTAINER" >&2 || true
    exit 1
}

tenant_files() { podman exec "$CONTAINER" sh -c 'ls /data/tenants | sort | tr "\n" " "'; }

code() {  # code <token-file|-> <path>
    local args=(-s -o /dev/null -w '%{http_code}')
    [ "$1" != "-" ] && args+=(-H "Cf-Access-Jwt-Assertion: $(cat "$WORK/jwks/token.$1")")
    curl "${args[@]}" "http://127.0.0.1:${PORT}$2"
}

expect() {  # expect <want> <label> <token> <path>
    local got
    got="$(code "$3" "$4")"
    if [ "$got" = "$1" ]; then pass "$2 -> $got"; else fail "$2: wanted $1, got $got"; fi
}

BEFORE="$(tenant_files)"
expect 200 "bound email (control arm)"      "$BOUND"   /api/binders
expect 403 "unbound email"                  "$UNBOUND" /api/binders
expect 401 "no token"                       -          /api/binders
expect 401 "token signed by an unknown key" badsig     /api/binders
expect 401 "expired token"                  expired    /api/binders
expect 401 "no token on a page"             -          /collection
expect 200 "/health needs no token"         -          /health
AFTER="$(tenant_files)"
if [ "$BEFORE" = "$AFTER" ]; then pass "nothing provisioned on lookup ($AFTER)"; else
    fail "lookup provisioned: before [$BEFORE] after [$AFTER]"; fi

cc="$(curl -s -D - -o /dev/null -H "Cf-Access-Jwt-Assertion: $(cat "$WORK/jwks/token.$BOUND")" \
      "http://127.0.0.1:${PORT}/collection" | tr -d '\r' | sed -n 's/^cache-control: //Ip')"
if [ "$cc" = "private, no-store" ]; then pass "tenant page is private, no-store"; else
    fail "tenant page cache-control is [$cc]"; fi

# --- single-tenant mode is unaffected -------------------------------------------
SINGLE_PORT="$(podman port "systemd-mtgc-${INSTANCE}" 8081/tcp 2>/dev/null | head -1 | cut -d: -f2 || true)"
if [ -n "$SINGLE_PORT" ]; then
    got="$(curl -sk -o /dev/null -w '%{http_code}' "https://127.0.0.1:${SINGLE_PORT}/api/binders")"
    if [ "$got" = "200" ]; then pass "single-tenant instance serves without an identity"; else
        fail "single-tenant instance answered $got"; fi
else
    fail "no single-tenant instance systemd-mtgc-${INSTANCE} to check"
fi

[ "$FAILED" -eq 0 ] || { echo "handles.sh: FAILED" >&2; exit 1; }
echo "handles.sh: all checks passed"
