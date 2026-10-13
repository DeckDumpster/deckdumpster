#!/usr/bin/env bash
#
# Print the reference of the dependency base image for this checkout, having
# made sure it exists in the active Podman store (sp-83v558).
#
# The image is deckdumpster-deps:<hash> where hash covers uv.lock and
# Containerfile.deps -- exactly the inputs of its layers. Only ~17 of 100 commits
# touch either, so most runs find it already built:
#
#   1. in the local store            -> use it
#   2. in ghcr (pull)                -> use it
#   3. neither                       -> build it; push when MTGC_DEPS_PUSH=1
#
# Step 2 failing is how "this hash is new" presents, so it is the one pull error
# that is not an error. A failed push is an error: CI sets MTGC_DEPS_PUSH=1 only
# after logging in, and a base that silently stops being published would put
# every later run back on the 3-minute path with nothing red.
#
# stdout carries only the final image reference; progress goes to stderr, so the
# callers can `DEPS_IMAGE="$(bash deploy/deps-image.sh)"`.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
# shellcheck source=deploy/store-lib.sh
. "$SCRIPT_DIR/store-lib.sh"

REGISTRY_REPO="${MTGC_DEPS_REPO:-ghcr.io/deckdumpster/deckdumpster-deps}"
HASH="$(cat "$REPO_DIR/uv.lock" "$REPO_DIR/Containerfile.deps" | sha256sum | cut -c1-16)"
REF="${REGISTRY_REPO}:${HASH}"

if podman image exists "$REF" >&2; then
    echo "==> deps base ${HASH}: in local store" >&2
elif podman pull -q "$REF" >&2 2>&1; then
    echo "==> deps base ${HASH}: pulled" >&2
else
    echo "==> deps base ${HASH}: new, building" >&2
    mapfile -t _uv_mount < <(mtgc_uv_cache_mount)
    podman build -t "$REF" -f "$REPO_DIR/Containerfile.deps" \
        "${_uv_mount[@]}" "$REPO_DIR" >&2
    if [ "${MTGC_DEPS_PUSH:-}" = "1" ]; then
        podman push "$REF" >&2
    fi
fi

printf '%s\n' "$REF"
