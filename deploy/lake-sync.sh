#!/usr/bin/env bash
#
# Mirror a lake zone's local files into the lake bucket (lakehouse 14).
#
#   lake-sync.sh <instance> raw        landing zone      -> s3://<lake>/raw/
#   lake-sync.sh <instance> catalog    Iceberg warehouse -> s3://<lake>/lake/catalog/
#
# Runs on the host as role/mtgc-lake, the only identity that may write those
# prefixes, and never with --delete: the raw zone is append-only, and a sync
# that could remove an object would be a second way to lose the lake. Both
# directories are content-addressed or append-only, so a re-run uploads nothing.
set -euo pipefail

INSTANCE="${1:?usage: lake-sync.sh <instance> raw|catalog}"
ZONE="${2:?usage: lake-sync.sh <instance> raw|catalog}"
CONF_DIR="${MTGC_CONFIG_DIR:-${HOME}/.config/mtgc}"
LOCAL_ROOT="${MTGC_LAKE_LOCAL_DIR:-${HOME}/.local/share/mtgc-lake/${INSTANCE}}"

for f in "${CONF_DIR}/${INSTANCE}.env" "${CONF_DIR}/${INSTANCE}/lake.env"; do
    [ -f "$f" ] && { set -a; . "$f"; set +a; }
done
[ -n "${MTGC_LAKE_S3_BUCKET:-}" ] \
    || { echo "lake-sync: MTGC_LAKE_S3_BUCKET is unset in ${CONF_DIR}/${INSTANCE}/lake.env" >&2; exit 1; }

case "$ZONE" in
    raw)     SRC="${LOCAL_ROOT}/raw";     DEST="s3://${MTGC_LAKE_S3_BUCKET}/raw/" ;;
    catalog) SRC="${LOCAL_ROOT}/iceberg"; DEST="s3://${MTGC_LAKE_S3_BUCKET}/lake/catalog/" ;;
    *) echo "lake-sync: zone must be raw or catalog, not '$ZONE'" >&2; exit 2 ;;
esac
[ -d "$SRC" ] || { echo "lake-sync: nothing to sync, $SRC does not exist" >&2; exit 1; }

ARGS=()
[ -n "${MTGC_LAKE_S3_ENDPOINT:-}" ] && ARGS=(--endpoint-url "$MTGC_LAKE_S3_ENDPOINT")
echo "lake-sync: $SRC -> $DEST"
AWS_PROFILE="${MTGC_LAKE_AWS_PROFILE:-mtgc-lake}" aws s3 sync "${ARGS[@]}" "$SRC/" "$DEST"
