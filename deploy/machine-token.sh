#!/usr/bin/env bash
#
# The machine client a host-local probe presents to /health (sp-3yi3j0).
#
# With MTGC_HEALTH_REQUIRE_AUTH=1 the app exempts nobody by address: a rootless podman
# publish rewrites the peer, so the tunnel and a host curl are indistinguishable and a
# loopback pass cannot exist. Every probe of a running instance therefore carries the
# client_credentials token deploy/cdn-check.sh mints, from the one file below. This is the
# one definition; origin-lib.sh, deploy.sh, handles.sh and cdn-check.sh all use it.
#
# Sourced; defines functions only.

# mtgc_machine_env_file <instance> — where the client id/secret live.
mtgc_machine_env_file() {
    echo "${MTGC_CDN_CHECK_ENV:-${HOME}/.config/mtgc/${1:-prod}/cdn-check.env}"
}

# mtgc_machine_token <instance> — prints a bearer token on stdout.
#   rc 0 token printed; rc 1 no client credentials configured; rc 2 the issuer refused them.
# Values already in the environment win; the file only fills what is unset.
mtgc_machine_token() {
    local file id secret url body token k v
    # A token already in hand wins (handles.sh drives the gate with the automation token).
    if [ -n "${MTGC_MACHINE_TOKEN:-}" ]; then printf '%s' "$MTGC_MACHINE_TOKEN"; return 0; fi
    file="$(mtgc_machine_env_file "$1")"
    id="${MTGC_CDN_CHECK_CLIENT_ID:-}"
    secret="${MTGC_CDN_CHECK_CLIENT_SECRET:-}"
    if [ -f "$file" ]; then
        for k in MTGC_CDN_CHECK_CLIENT_ID MTGC_CDN_CHECK_CLIENT_SECRET; do
            v="$(grep -E "^${k}=" "$file" | tail -n1 | cut -d= -f2-)"
            if [ "$k" = MTGC_CDN_CHECK_CLIENT_ID ] && [ -z "$id" ]; then id="$v"; fi
            if [ "$k" = MTGC_CDN_CHECK_CLIENT_SECRET ] && [ -z "$secret" ]; then secret="$v"; fi
        done
    fi
    [ -n "$id" ] && [ -n "$secret" ] || return 1
    url="${MTGC_CDN_CHECK_TOKEN_URL:-${MTGC_OIDC_ISSUER:-https://id.gantt.pub}/api/oidc/token}"
    body="$(curl -sS -m 20 -X POST "$url" \
        --data-urlencode grant_type=client_credentials \
        --data-urlencode "client_id=${id}" \
        --data-urlencode "client_secret=${secret}" 2>/dev/null)"
    token="$(printf '%s' "$body" | grep -oE '"access_token": *"[^"]+"' | head -n1 | sed -E 's/.*: *"([^"]+)"/\1/')"
    [ -n "$token" ] || return 2
    printf '%s' "$token"
}

# mtgc_machine_auth <instance> — sets MACHINE_AUTH to curl arguments: the Bearer header, or
# empty when this host holds no client (a single-tenant instance, which gates nothing).
# A client that is configured but refused is an error (rc 1): a probe must not fall back to
# going unauthenticated and then read the 401 as "alive".
mtgc_machine_auth() {
    local token rc=0
    MACHINE_AUTH=()
    token="$(mtgc_machine_token "$1")" || rc=$?
    case "$rc" in
        0) MACHINE_AUTH=(-H "Authorization: Bearer ${token}") ;;
        1) ;;
        *) echo "machine-token: the issuer refused the machine client for '$1'" >&2; return 1 ;;
    esac
}
