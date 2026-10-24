#!/usr/bin/env bash
#
# The DR restore drill against the REAL buckets (lakehouse 14). Run by Ryan or the
# Concierge on the deploy box; never by an aeon, never by CI.
#
#   lake-drill.sh <instance> --master-key FILE [--partition RUN_ID]
#
# Proves the three things deploy/LAKE-DR.md rests on, in the order it restores
# them, entirely into a scratch directory (live files and buckets are only read):
#
#   1. REGISTRY FIRST  restored from its Litestream replica, as the runbook does.
#   2. MASTER KEY      FILE is the copy out of the password manager. Its
#                      fingerprint must equal the box's key (when the box has one):
#                      a drill with a key nobody can match proves nothing.
#   3. CATALOGUE       the named raw partition (default: the newest complete one)
#                      is pulled from s3://<lake>/raw/ and derived offline in a job
#                      container; cards / printings / sets / mtgjson_printings row
#                      counts must equal the served catalogue's. A partition older
#                      than the served one is a deliberate difference: pass the one
#                      the box derived from.
#   4. ZONE            zone_holdings is rebuilt by `mtg lake readback` from the
#                      bucket alone, under the restored registry and that key, and
#                      its per-tenant row counts must equal the live zone's.
#
# Exit 0 only if every claim held. Any failure names the step and leaves the
# scratch directory in place for inspection (its path is printed).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=deploy/litestream-lib.sh
. "$SCRIPT_DIR/litestream-lib.sh"
# shellcheck source=deploy/store-lib.sh
. "$SCRIPT_DIR/store-lib.sh"

INSTANCE="${1:?usage: lake-drill.sh <instance> --master-key FILE [--partition RUN_ID]}"
shift
KEY="" PARTITION=""
while [ $# -gt 0 ]; do
    case "$1" in
        --master-key) KEY="${2:?}"; shift 2 ;;
        --partition) PARTITION="${2:?}"; shift 2 ;;
        *) echo "lake-drill: unknown argument $1" >&2; exit 2 ;;
    esac
done
[ -f "$KEY" ] || { echo "lake-drill: --master-key FILE is required (the password-manager copy)" >&2; exit 2; }

CONF_DIR="${MTGC_CONFIG_DIR:-${HOME}/.config/mtgc}"
for f in "${CONF_DIR}/${INSTANCE}.env" "${CONF_DIR}/${INSTANCE}/lake.env"; do
    [ -f "$f" ] && { set -a; . "$f"; set +a; }
done
: "${MTGC_LAKE_S3_BUCKET:?lake.env must name MTGC_LAKE_S3_BUCKET}"
: "${MTGC_LAKE_TENANT_URI:?lake.env must name MTGC_LAKE_TENANT_URI}"

# The drill's job containers must run in the store the instance lives in.
mtgc_store_adopt_instance "$INSTANCE"
mtgc_store_activate

HOME_DIR="$(mtgc_ls_home "$INSTANCE")"
SCRATCH="$(mktemp -d)"
IMAGE="localhost/mtgc:${INSTANCE}"
step() { echo "== lake-drill: $*"; }
fail() { echo "lake-drill: FAILED at $1 -- scratch kept at $SCRATCH" >&2; exit 1; }

# Scratch is mode 700 and removed on success only: it holds a master key copy.
chmod 700 "$SCRATCH"
mkdir -p "$SCRATCH/home/lake" "$SCRATCH/raw" "$SCRATCH/key"
install -m 600 "$KEY" "$SCRATCH/key/tenant-master.key"

jobrun() {   # jobrun <aws-profile> <extra podman args...> -- <command...>
    local profile="$1"; shift
    podman run --rm --env-file "${CONF_DIR}/${INSTANCE}.env" --env-file "${CONF_DIR}/${INSTANCE}/lake.env" \
        -e MTGC_HOME=/scratch/home -e MTGC_SHARED_DB= -v "$SCRATCH":/scratch:Z \
        -e AWS_PROFILE="$profile" -v "$HOME/.aws":/root/.aws:ro,Z \
        -e MTGC_LAKE_MASTER_KEY_FILE=/scratch/key/tenant-master.key \
        -e MTGC_LAKE_RAW_DIR=/scratch/raw "$@"
}

step "1/4 registry from its replica"
litestream restore -o "$SCRATCH/home/registry.sqlite" "$(mtgc_ls_restore_url "$INSTANCE" registry)" \
    || fail "registry restore"
mapfile -t IDS < <(mtgc_ls_tenant_ids "$SCRATCH/home/registry.sqlite")
[ "${#IDS[@]}" -ge 1 ] || fail "registry restore (no active tenant in the restored registry)"
echo "   ${#IDS[@]} active tenant(s)"

step "2/4 master key fingerprint"
fp() { python3 -I - "$1" <<'PY'
import hashlib, sys
print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest()[:16])
PY
}
LIVE_KEY="${CONF_DIR}/${INSTANCE}/tenant-master.key"
if [ -f "$LIVE_KEY" ]; then
    [ "$(fp "$KEY")" = "$(fp "$LIVE_KEY")" ] || fail "master key (the password-manager copy is not the box's key)"
    echo "   password-manager copy equals the box's key"
else
    echo "   the box has no key (true DR): trusting the supplied copy; step 4 proves it by decrypting"
fi

step "3/4 catalogue cold rebuild from raw/"
LAKE_PROFILE="${MTGC_LAKE_AWS_PROFILE:-mtgc-lake}"
S3=(aws s3 --profile "$LAKE_PROFILE")
[ -z "${MTGC_LAKE_S3_ENDPOINT:-}" ] || S3+=(--endpoint-url "$MTGC_LAKE_S3_ENDPOINT")
if [ -z "$PARTITION" ]; then
    PARTITION="$("${S3[@]}" ls --recursive "s3://${MTGC_LAKE_S3_BUCKET}/raw/" \
        | python3 -I -c '
import re, sys
need = {("scryfall", "default_cards"), ("mtgjson", "allprintings"), ("mtgjson", "meta")}
runs = {}
for line in sys.stdin:
    m = re.search(r"source=([^/]+)/dataset=([^/]+)/ingest_date=[^/]+/run=([^/]+)/_manifest.json", line)
    if m:
        runs.setdefault(m.group(3), set()).add((m.group(1), m.group(2)))
ok = [r for r, have in runs.items() if need <= have]
print(max(ok) if ok else "")')"
fi
[ -n "$PARTITION" ] || fail "catalogue (no complete raw partition in the bucket)"
echo "   partition run=$PARTITION"
"${S3[@]}" sync "s3://${MTGC_LAKE_S3_BUCKET}/raw/" "$SCRATCH/raw" --exclude '*' --include "*run=${PARTITION}/*" >/dev/null \
    || fail "catalogue (fetching the partition manifests)"
python3 -I - "$SCRATCH/raw" <<'PY' > "$SCRATCH/objects.txt" || fail "catalogue (reading manifests)"
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
for m in root.glob("source=*/dataset=*/ingest_date=*/run=*/_manifest.json"):
    for e in json.loads(m.read_text())["entries"]:
        print(e["object"])
PY
while IFS= read -r obj; do
    [ -f "$SCRATCH/raw/$obj" ] && continue
    mkdir -p "$(dirname "$SCRATCH/raw/$obj")"
    "${S3[@]}" cp "s3://${MTGC_LAKE_S3_BUCKET}/raw/${obj}" "$SCRATCH/raw/$obj" >/dev/null \
        || fail "catalogue (object $obj is named by a manifest but missing from the bucket)"
done < "$SCRATCH/objects.txt"
jobrun "$LAKE_PROFILE" --entrypoint mtg "$IMAGE" data derive --run "$PARTITION" --raw-root /scratch/raw \
    || fail "catalogue (derive from the partition)"

LIVE_SHARED="$HOME_DIR/shared.sqlite"
[ -f "$LIVE_SHARED" ] || LIVE_SHARED="$HOME_DIR/collection.sqlite"
python3 -I - "$SCRATCH/home" "$LIVE_SHARED" <<'PY' || fail "catalogue (row counts differ from the served catalogue)"
import glob, sqlite3, sys
rebuilt = sorted(glob.glob(sys.argv[1] + "/*.sqlite") + glob.glob(sys.argv[1] + "/**/collection.sqlite", recursive=True))
rebuilt = [p for p in rebuilt if not p.endswith("registry.sqlite")]
if not rebuilt:
    sys.exit("no rebuilt catalogue under " + sys.argv[1])
def counts(path):
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    return {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("cards", "printings", "sets", "mtgjson_printings")}
a, b = counts(rebuilt[0]), counts(sys.argv[2])
for t in a:
    print(f"   {t}: rebuilt {a[t]}, served {b[t]}")
sys.exit(0 if a == b else 1)
PY

step "4/4 zone read-back from the bucket alone"
jobrun mtgc-tenant --entrypoint mtg "$IMAGE" lake readback || fail "zone (read-back; a wrong key fails here)"
python3 -I - "$SCRATCH/home/lake/zone.sqlite" "$HOME_DIR/lake/zone.sqlite" <<'PY' || fail "zone (zone_holdings per tenant differ from the live zone)"
import sqlite3, sys
def counts(path):
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    return dict(c.execute("SELECT database_id, COUNT(*) FROM zone_holdings GROUP BY database_id"))
a = counts(sys.argv[1])
try:
    b = counts(sys.argv[2])
except sqlite3.OperationalError:
    print("   no live zone state (true DR): rebuilt", sum(a.values()), "holding row(s) from the bucket")
    sys.exit(0)
for k in sorted(set(a) | set(b)):
    print(f"   {k}: rebuilt {a.get(k, 0)}, live {b.get(k, 0)}")
sys.exit(0 if a == b else 1)
PY

rm -rf "$SCRATCH"
echo "lake-drill: OK -- registry, master key, catalogue partition ${PARTITION} and the zone all restored from the real buckets"
