#!/usr/bin/env bash
#
# Remove an alternate container store outright — every container, image and
# volume in it, then the store root and its runroot (de-3mo).
#
# deploy/teardown.sh removes an INSTANCE and leaves the store standing, because
# the store is shared by every instance on the box. Nothing removed the store
# itself, so a box accumulates one forever.
#
# This runs the recipe documented in deploy/store-lib.sh's header. It NEVER runs
# `podman system reset`, which is not scoped by --root/--runroot and took prod
# down when it was aimed at a throwaway store.
#
# With no alternate store configured it exits non-zero rather than defaulting to
# Podman's store — that one is prod's.
#
# Usage:
#   bash deploy/store-teardown.sh
#   MTGC_STORE_ROOT=/some/dir bash deploy/store-teardown.sh
#
set -euo pipefail

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# shellcheck source=deploy/store-lib.sh
. "$SCRIPT_DIR/store-lib.sh"

# Same resolution order as .github/workflows/ci.yml: an explicit MTGC_STORE_ROOT
# wins, the host's ~/.config/mtgc/store.env answers when it is unset, and
# neither means the default store — which mtgc_store_teardown refuses.
mtgc_store_load_config

if [ -z "${MTGC_STORE_ROOT:-}" ]; then
    echo "No alternate container store configured — nothing to remove."
    echo "  (nothing in \$MTGC_STORE_ROOT or ~/.config/mtgc/store.env)"
    echo "  Podman's default store is prod's; this command will not touch it."
    exit 1
fi

echo "==> Store to remove: ${MTGC_STORE_ROOT}"
if [ -d "${MTGC_STORE_ROOT}/storage" ]; then
    echo "    (currently $(du -sh "${MTGC_STORE_ROOT}" 2>/dev/null | cut -f1) on disk)"
fi

mtgc_store_teardown

echo "==> Store removed."
echo "    The podman shim lived inside it — start a new shell rather than"
echo "    trusting this one, whose PATH now points at nothing."
