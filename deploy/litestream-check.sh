#!/usr/bin/env bash
#
# Replica freshness check (sp-sal0ci, pd-1717): liveness is not freshness.
#
#   litestream-check.sh [instance]        (default: prod)
#
# A Litestream sidecar can show systemd `active` while error-looping on
# AccessDenied and replicating nothing. This asks the replica, and goes red
# (exit 1, and an alert) when:
#   - the replica cannot be listed, or holds no objects;
#   - a sampled tenant's replica cannot be RESTORED, or restores to a database
#     that fails PRAGMA integrity_check — an unrestorable replica is not a backup;
#   - the replica position has not advanced although the live database has been
#     written since the last run. The position is the newest object key under
#     the replica prefix; the last one seen is kept in $MTGC_STATE_DIR.
#
# The sample rotates with the day, so every tenant is restored over time.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=deploy/litestream-lib.sh
. "$SCRIPT_DIR/litestream-lib.sh"

INSTANCE="${1:-prod}"
CONF_DIR="${MTGC_CONFIG_DIR:-${HOME}/.config/mtgc}"
[ -f "${CONF_DIR}/alerts.env" ]      && { set -a; . "${CONF_DIR}/alerts.env";      set +a; }
[ -f "${CONF_DIR}/${INSTANCE}.env" ] && { set -a; . "${CONF_DIR}/${INSTANCE}.env"; set +a; }

STATE_DIR="${MTGC_STATE_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/mtgc}"
mkdir -p "$STATE_DIR"
STATE="$STATE_DIR/litestream-${INSTANCE}.position"

stale() {
    echo "litestream-check: STALE — $1" >&2
    "$SCRIPT_DIR/alert.sh" "MTGC replica STALE (${INSTANCE})" "$1" || true
    exit 1
}

BUCKET="$(mtgc_ls_bucket)" || stale "MTGC_BACKUP_S3_BUCKET is unset — there is no replica to verify"
HOME_DIR="$(mtgc_ls_home "$INSTANCE")" || stale "cannot locate the instance's data"
ENDPOINT_ARGS=()
[ -n "${MTGC_BACKUP_S3_ENDPOINT:-}" ] && ENDPOINT_ARGS=(--endpoint-url "${MTGC_BACKUP_S3_ENDPOINT}")

LISTING="$(aws s3api list-objects-v2 "${ENDPOINT_ARGS[@]}" --bucket "$BUCKET" \
    --prefix "mtgc-${INSTANCE}/litestream/" \
    --query 'Contents[].[LastModified,Key]' --output text 2>&1)" \
    || stale "could not list the replica prefix: $(printf '%s' "$LISTING" | tail -n1)"
LISTING="$(printf '%s\n' "$LISTING" | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}T' | sort || true)"
[ -n "$LISTING" ] || stale "s3://${BUCKET}/mtgc-${INSTANCE}/litestream/ holds NO objects"
POSITION="$(printf '%s\n' "$LISTING" | tail -n1)"

# Position: advanced since the last run? Only demanded if the database has been
# written since — an idle database has nothing new to replicate.
NEWEST_DB="$(ls -1t "$HOME_DIR"/collection.sqlite* "$HOME_DIR"/registry.sqlite* \
    "$HOME_DIR"/tenants/*.sqlite* 2>/dev/null | head -n1 || true)"
if [ -f "$STATE" ] && [ "$(cat "$STATE")" = "$POSITION" ] \
        && [ -n "$NEWEST_DB" ] && [ "$NEWEST_DB" -nt "$STATE" ]; then
    stale "replica position did not advance (still ${POSITION##*[[:space:]]}) although ${NEWEST_DB} was written since the last check"
fi

# Restore a sample.
SCRATCH="$(mktemp -d)"
trap 'rm -rf "$SCRATCH"' EXIT
if [ -f "$HOME_DIR/registry.sqlite" ]; then
    mapfile -t IDS < <(mtgc_ls_tenant_ids "$HOME_DIR/registry.sqlite")
else
    IDS=()
fi
if [ "${#IDS[@]}" -gt 0 ]; then
    ID="${IDS[$(( $(date +%s) / 86400 % ${#IDS[@]} ))]}"
    SAMPLE="$SCRATCH/${ID}.sqlite"
    URL="$(mtgc_ls_replica_url "$INSTANCE" tenants)/${ID}.sqlite"
    NAME="tenant ${ID}"
else
    SAMPLE="$SCRATCH/collection.sqlite"
    URL="$(mtgc_ls_replica_url "$INSTANCE" collection)"
    NAME="collection.sqlite"
fi
litestream restore -o "$SAMPLE" "$URL" >/dev/null 2>&1 || stale "could not restore ${NAME} from ${URL}"
python3 -I - "$SAMPLE" <<'PY' || stale "restored ${NAME} fails PRAGMA integrity_check"
import sqlite3, sys
r = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True).execute("PRAGMA integrity_check").fetchall()
sys.exit(0 if r == [("ok",)] else 1)
PY

printf '%s' "$POSITION" > "$STATE"
echo "litestream-check: OK — restored ${NAME}; position ${POSITION##*[[:space:]]}"
