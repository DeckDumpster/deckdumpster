#!/usr/bin/env bash
#
# Which listener does a RUNNING instance serve, and is it alive? (sp-8lil3y)
#
# The one definition. Single-tenant serves HTTPS on container port 8081.
# Multi-tenant serves only the plain-HTTP listener on container 8080 ("port 8081
# is not served"), published on the host loopback, and answers 401 to every
# route outside PUBLIC_ROUTES until it is shown an Access identity. Three probes
# (deploy.sh, cdn-check, handles.sh) each hard-coded one side of that and
# reported a healthy instance down; this is the fourth place to look, not a
# fourth copy. Setup paths (ci.sh, setup.sh, mac-*) create single-tenant
# instances and keep naming 8081 — they do not probe a running instance.
#
# Sourced; defines functions only. Reads the published port through the same
# `podman` the caller already has configured for the instance's store.

# shellcheck source=store-lib.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/store-lib.sh"
# shellcheck source=machine-token.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/machine-token.sh"

# mtgc_origin_resolve <instance> — sets, for the instance's mode:
#   ORIGIN_MODE   multitenant | single
#   ORIGIN_PORT   host port
#   ORIGIN_URL    scheme://127.0.0.1:port (never localhost: it can resolve to ::1, which the publish answers with a reset)
#   ORIGIN_PROBE  path that answers 200 when the app is up
# Returns 1 (and prints why) when no listener is published: a container that is
# down has no published port, so this is also the "container down" failure.
mtgc_origin_resolve() {
    local instance="$1" container="systemd-mtgc-$1" port
    # The instance's own podman store, as deploy.sh reads it (de-3mo).
    mtgc_store_adopt_instance "$instance"
    mtgc_store_activate
    port="$(podman port "$container" 8080/tcp 2>/dev/null | grep -oP ':\K[0-9]+' | head -1 || true)"
    if [ -n "$port" ]; then
        ORIGIN_MODE=multitenant
        ORIGIN_PORT="$port"
        ORIGIN_URL="http://127.0.0.1:${port}"
        ORIGIN_PROBE=/health
        return 0
    fi
    port="$(podman port "$container" 8081/tcp 2>/dev/null | grep -oP ':\K[0-9]+' | head -1 || true)"
    if [ -n "$port" ]; then
        ORIGIN_MODE=single
        ORIGIN_PORT="$port"
        ORIGIN_URL="https://127.0.0.1:${port}"
        ORIGIN_PROBE=/
        return 0
    fi
    echo "origin: no published listener for ${container} (is the container running?)" >&2
    return 1
}

# mtgc_origin_alive <instance> — resolve, then ask the listener, carrying the machine
# token (machine-token.sh) because /health is gated and no address is exempt. Alive means
# a 2xx, or, on the multi-tenant listener, its 401 identity challenge (a server that
# answers a challenge is up; one that answers nothing is not). Anything else, including
# no connection, is down.
mtgc_origin_alive() {
    mtgc_origin_resolve "$1" || return 1
    mtgc_machine_auth "$1" || return 1
    local code
    code="$(curl -sk --connect-timeout 3 -m 10 -o /dev/null -w '%{http_code}' \
        "${MACHINE_AUTH[@]}" "${ORIGIN_URL}${ORIGIN_PROBE}" 2>/dev/null || true)"
    case "$code" in
        2??) return 0 ;;
        401) [ "$ORIGIN_MODE" = multitenant ] && return 0 ;;
    esac
    echo "origin: ${ORIGIN_URL}${ORIGIN_PROBE} answered '${code:-nothing}'" >&2
    return 1
}
