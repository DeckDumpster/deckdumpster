#!/usr/bin/env bash
#
# Mirror a lake zone's local files into the lake bucket (lakehouse 14).
#
#   lake-sync.sh <instance> raw        landing zone      -> s3://<lake>/raw/
#   lake-sync.sh <instance> catalog    Iceberg warehouse -> s3://<lake>/lake/catalog/
#
# Runs on the host as the mtgc-lake identity, the only identity that may write those
# prefixes, and never with --delete: the raw zone is append-only, and a sync
# that could remove an object would be a second way to lose the lake. Both
# directories are content-addressed or append-only, so a re-run uploads nothing.
set -euo pipefail

INSTANCE="${1:?usage: lake-sync.sh <instance> raw|catalog}"
ZONE="${2:?usage: lake-sync.sh <instance> raw|catalog}"
CONF_DIR="${MTGC_CONFIG_DIR:-${HOME}/.config/mtgc}"
LOCAL_ROOT="${MTGC_LAKE_LOCAL_DIR:-${HOME}/.local/share/mtgc-lake/${INSTANCE}}"

# An ExecStartPost process loses its unit metadata, so its stderr never reaches the journal
# under the unit. Every refusal also goes to the journal under an explicit identifier.
refuse() {
    echo "lake-sync: $1" >&2
    logger -t "mtgc-lake-sync-${INSTANCE}" -p user.err -- "lake-sync: $1" || true
    exit "${2:-1}"
}

for f in "${CONF_DIR}/${INSTANCE}.env" "${CONF_DIR}/${INSTANCE}/lake.env"; do
    [ -f "$f" ] && { set -a; . "$f"; set +a; }
done
[ -n "${MTGC_LAKE_S3_BUCKET:-}" ] \
    || refuse "MTGC_LAKE_S3_BUCKET is unset in ${CONF_DIR}/${INSTANCE}/lake.env (bash deploy/lake-config.sh ${INSTANCE})"

case "$ZONE" in
    raw)     SRC="${LOCAL_ROOT}/raw";     DEST="s3://${MTGC_LAKE_S3_BUCKET}/raw/" ;;
    catalog) SRC="${LOCAL_ROOT}/iceberg"; DEST="s3://${MTGC_LAKE_S3_BUCKET}/lake/catalog/" ;;
    *) refuse "zone must be raw or catalog, not '$ZONE'" 2 ;;
esac
[ -d "$SRC" ] || refuse "nothing to sync, $SRC does not exist"

ARGS=()
[ -n "${MTGC_LAKE_S3_ENDPOINT:-}" ] && ARGS=(--endpoint-url "$MTGC_LAKE_S3_ENDPOINT")
echo "lake-sync: $SRC -> $DEST"
AWS_PROFILE="${MTGC_LAKE_AWS_PROFILE:-mtgc-lake}" aws s3 sync "${ARGS[@]}" "$SRC/" "$DEST" \
    || refuse "aws s3 sync $SRC -> $DEST failed"

# The raw zone is a second copy once S3 holds it, and the root disk is the deploy floor's
# subject (sp-ol9a3q). Prune against the bucket's own listing, so only a file S3 confirms
# at the same size is ever removed; the newest runs stay for derive.
if [ "$ZONE" = raw ]; then
    LISTING="$(mktemp)"; trap 'rm -f "$LISTING"' EXIT
    AWS_PROFILE="${MTGC_LAKE_AWS_PROFILE:-mtgc-lake}" aws s3 ls "${ARGS[@]}" --recursive "$DEST" \
        | awk '{k=$4; sub(/^raw\//, "", k); print $3, k}' > "$LISTING" \
        || refuse "aws s3 ls $DEST failed; local raw left unpruned"
    python3 "$(dirname "$0")/../mtg_collector/lake/prune_raw.py" --root "$SRC" --listing "$LISTING" \
        --keep "${MTGC_LAKE_KEEP_RUNS:-2}" || refuse "prune of $SRC failed"
fi
echo "lake-sync: local lake $(du -sh "$LOCAL_ROOT" | cut -f1) at $LOCAL_ROOT"
