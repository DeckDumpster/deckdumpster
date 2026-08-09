#!/usr/bin/env bash
#
# Render the Quadlet unit for an MTGC instance to stdout.
#
# Usage:
#   bash deploy/render-quadlet.sh <instance> <port-mapping> <http-port> [template]
#
#   <instance>      instance name, substituted for {{INSTANCE}}
#   <port-mapping>  host:container mapping for the HTTPS listener, e.g. "8081:8081"
#                   or ":8081" to let Podman auto-assign
#   <http-port>     host port for the plaintext listener, or "" for none.
#                   When set, the plaintext listener is published on LOOPBACK
#                   ONLY (127.0.0.1). The bind address is hardcoded here and is
#                   deliberately not operator-configurable: a 0.0.0.0 publish
#                   would expose plaintext to the LAN.
#   [template]      path to mtgc.container (defaults to the one beside this script)
#
# With an empty <http-port> the output is byte-identical to a render that has no
# plaintext publish at all — the {{HTTP_PUBLISH}} line is deleted, not blanked.
set -euo pipefail

if [ $# -lt 3 ]; then
    echo "Usage: bash deploy/render-quadlet.sh <instance> <port-mapping> <http-port> [template]" >&2
    exit 1
fi

INSTANCE="$1"
PORT_MAPPING="$2"
HTTP_PORT="$3"
TEMPLATE="${4:-$(cd "$(dirname "$0")" && pwd)/mtgc.container}"

if [ -n "$HTTP_PORT" ]; then
    if ! [[ "$HTTP_PORT" =~ ^[0-9]+$ ]]; then
        echo "ERROR: http port must be numeric, got: $HTTP_PORT" >&2
        exit 1
    fi
    HTTP_PUBLISH_SED="s|^{{HTTP_PUBLISH}}\$|PublishPort=127.0.0.1:${HTTP_PORT}:8080|"
else
    HTTP_PUBLISH_SED="/^{{HTTP_PUBLISH}}\$/d"
fi

sed \
    -e "s|{{INSTANCE}}|${INSTANCE}|g" \
    -e "s|{{PORT}}:8081|${PORT_MAPPING}|g" \
    -e "$HTTP_PUBLISH_SED" \
    "$TEMPLATE"
