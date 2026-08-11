#!/usr/bin/env bash
#
# Render the Quadlet unit for an MTGC instance to stdout.
#
# Usage:
#   bash deploy/render-quadlet.sh <instance> <port-mapping> <http-port> <tls-certs> [template]
#
#   <instance>      instance name, substituted for {{INSTANCE}}
#   <port-mapping>  host:container mapping for the HTTPS listener, e.g. "8081:8081"
#                   or ":8081" to let Podman auto-assign
#   <http-port>     host port for the plaintext listener, or "" for none.
#                   When set, the plaintext listener is published on LOOPBACK
#                   ONLY (127.0.0.1). The bind address is hardcoded here and is
#                   deliberately not operator-configurable: a 0.0.0.0 publish
#                   would expose plaintext to the LAN.
#   <tls-certs>     host directory holding externally-obtained certificates
#                   (e.g. "%h/.config/mtgc/certs"), or "" for none. When set it
#                   is mounted at /certs READ-ONLY; the container never writes
#                   there and never obtains a certificate. The container path
#                   and the :ro flag are hardcoded here, not operator-supplied.
#   [template]      path to mtgc.container (defaults to the one beside this script)
#
# With an empty <http-port> / <tls-certs> the output is byte-identical to a render
# that has no plaintext publish and no cert mount at all — the {{HTTP_PUBLISH}} and
# {{TLS_MOUNT}} lines are deleted, not blanked.
set -euo pipefail

if [ $# -lt 4 ]; then
    echo "Usage: bash deploy/render-quadlet.sh <instance> <port-mapping> <http-port> <tls-certs> [template]" >&2
    exit 1
fi

INSTANCE="$1"
PORT_MAPPING="$2"
HTTP_PORT="$3"
TLS_CERTS="$4"
TEMPLATE="${5:-$(cd "$(dirname "$0")" && pwd)/mtgc.container}"

if [ -n "$HTTP_PORT" ]; then
    if ! [[ "$HTTP_PORT" =~ ^[0-9]+$ ]]; then
        echo "ERROR: http port must be numeric, got: $HTTP_PORT" >&2
        exit 1
    fi
    HTTP_PUBLISH_SED="s|^{{HTTP_PUBLISH}}\$|PublishPort=127.0.0.1:${HTTP_PORT}:8080|"
else
    HTTP_PUBLISH_SED="/^{{HTTP_PUBLISH}}\$/d"
fi

if [ -n "$TLS_CERTS" ]; then
    # Absolute (or %h-relative) path only, and no character that could break out
    # of the Volume= field: ':' and ',' separate its parts, '|' is the sed
    # delimiter, '&' and '\' are sed replacement metacharacters.
    if ! [[ "$TLS_CERTS" =~ ^(/|%h/)[A-Za-z0-9._%+@/-]*$ ]]; then
        echo "ERROR: tls certs dir must be an absolute or %h/ path with no ':' or ',', got: $TLS_CERTS" >&2
        exit 1
    fi
    TLS_MOUNT_SED="s|^{{TLS_MOUNT}}\$|Volume=${TLS_CERTS}:/certs:ro,Z|"
else
    TLS_MOUNT_SED="/^{{TLS_MOUNT}}\$/d"
fi

sed \
    -e "s|{{INSTANCE}}|${INSTANCE}|g" \
    -e "s|{{PORT}}:8081|${PORT_MAPPING}|g" \
    -e "$HTTP_PUBLISH_SED" \
    -e "$TLS_MOUNT_SED" \
    "$TEMPLATE"
