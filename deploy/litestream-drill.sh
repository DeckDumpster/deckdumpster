#!/usr/bin/env bash
#
# The restore drill (sp-sal0ci): restore a NON-FIRST tenant from its replica and
# prove nothing else moved.
#
#   litestream-drill.sh [instance]        (default: prod)
#
# Restore order is the registry first, then the tenant — the tenant is chosen
# by reading the restored registry, not the live one. The first tenant is
# skipped on purpose: a drill that only ever restores tenant one proves a path
# that works for one tenant. With fewer than two the drill FAILS; it cannot pass
# on a population that has no non-first member.
#
# Everything is restored into a scratch directory. The live files are only read,
# and their sha256 is compared before and after: any drift is a failure.
#
#   MTGC_DRILL_CHECK_LIVE=0 skips the comparison of restored against live data
#   (a drill on a restore-only box); the untouched-others check always runs.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=deploy/litestream-lib.sh
. "$SCRIPT_DIR/litestream-lib.sh"

INSTANCE="${1:-prod}"
CONF_DIR="${MTGC_CONFIG_DIR:-${HOME}/.config/mtgc}"
[ -f "${CONF_DIR}/${INSTANCE}.env" ] && { set -a; . "${CONF_DIR}/${INSTANCE}.env"; set +a; }

HOME_DIR="$(mtgc_ls_home "$INSTANCE")"
SCRATCH="$(mktemp -d)"
trap 'rm -rf "$SCRATCH"' EXIT

fail() { echo "litestream-drill: FAILED — $1" >&2; exit 1; }

fingerprint() {   # sha256 of every live database file except $1
    local skip="$1" f
    for f in "$HOME_DIR"/registry.sqlite "$HOME_DIR"/tenants/*.sqlite; do
        [ -e "$f" ] || continue
        [ "$(basename "$f" .sqlite)" = "$skip" ] && continue
        sha256sum "$f"
    done
}

# 1. Registry first.
litestream restore -o "$SCRATCH/registry.sqlite" "$(mtgc_ls_replica_url "$INSTANCE" registry)" \
    || fail "could not restore the registry"
mapfile -t IDS < <(mtgc_ls_tenant_ids "$SCRATCH/registry.sqlite")
[ "${#IDS[@]}" -ge 2 ] \
    || fail "the registry holds ${#IDS[@]} tenant(s); a drill needs a non-first tenant to restore"
TARGET="${IDS[1]}"

# Snapshot the others only now that the target is known. The live databases are
# WAL-mode and being written, so byte-identity is asserted for what the drill is
# responsible for not touching, over the interval the drill ran.
BEFORE="$(fingerprint "$TARGET")"

# 2. Then the tenant.
litestream restore -o "$SCRATCH/${TARGET}.sqlite" "$(mtgc_ls_replica_url "$INSTANCE" tenants)/${TARGET}.sqlite" \
    || fail "could not restore tenant $TARGET"

python3 -I - "$SCRATCH/${TARGET}.sqlite" <<'PY' || fail "restored tenant $TARGET failed PRAGMA integrity_check"
import sqlite3, sys
r = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True).execute("PRAGMA integrity_check").fetchall()
sys.exit(0 if r == [("ok",)] else 1)
PY

if [ "${MTGC_DRILL_CHECK_LIVE:-1}" = "1" ] && [ -f "$HOME_DIR/tenants/${TARGET}.sqlite" ]; then
    python3 -I - "$SCRATCH/${TARGET}.sqlite" "$HOME_DIR/tenants/${TARGET}.sqlite" <<'PY' \
        || fail "restored tenant $TARGET differs in schema version from the live one"
import sqlite3, sys
v = [sqlite3.connect(f"file:{p}?mode=ro", uri=True).execute("PRAGMA user_version").fetchone()[0] for p in sys.argv[1:]]
sys.exit(0 if v[0] == v[1] else 1)
PY
fi

AFTER="$(fingerprint "$TARGET")"
[ "$BEFORE" = "$AFTER" ] || fail "the drill changed another tenant's live files"

echo "litestream-drill: OK — registry and tenant ${TARGET} restored; ${#IDS[@]} tenants, the other $((${#IDS[@]} - 1)) byte-identical"
