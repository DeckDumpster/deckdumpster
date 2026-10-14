#!/usr/bin/env bash
# Container-tier gate (lakehouse bead 10): the TENANT ZONE is governed, not just
# described.  Run by deploy/ci.sh (integration tier).  Standalone:
#
#   bash tests/lake/tenant_zone.sh          # full run + teardown
#   KEEP=1 bash tests/lake/tenant_zone.sh   # leave MinIO + WORK up for poking
#
# The tenant zone (`tenant/`) and the catalog zone (`raw/`, `lake/`) share one
# bucket.  The only thing separating them is a pair of credential policies and a
# lifecycle rule, and a policy is one misconfiguration from being nothing while
# looking identical from the outside.  Every claim below is seen GREEN and RED:
#
#   §1/§1b  retention applied by the real script; it refuses an unnamed bucket
#           and a backup bucket
#   §2      the retention check goes red with the EXIT CODE asserted: a
#           whole-bucket rule, 365 days and a second rule reaching raw/ give 1;
#           the rule deleted gives 3 — then green again
#   §2b     the same CORRECT rule read by a real credential MinIO really denies
#           gives 4, not 3, names s3:GetLifecycleConfiguration, never says ABSENT
#   §3-§5   the two identities carry the rendered documents, each CAN reach its
#           own zone (so a denial is a denial, not an absence), and neither can
#           read, list or write the other's; the catalog zone is append-only
#   §6      the SAME assertion functions go red when a credential is replaced by
#           a whole-bucket grant — then green again
#   §6b     a whole-bucket grant added BESIDE either policy still cannot cross
#   §7      the fixtures leave the tenant zone empty and the catalog untouched
#
# The policy documents are applied VERBATIM, bucket substituted, by the real
# deploy/setup-tenant-zone.sh: an IAM policy document is the same dialect for
# AWS and MinIO, which is the only reason this is testable rather than trusted.
#
# Prod-safe: its own podman network, MinIO, temp dir and bucket.  No real tenant
# data anywhere — every byte under tenant/ is a literal governance probe.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

MINIO_IMAGE=${MINIO_IMAGE:-ghcr.io/deckdumpster/minio:RELEASE.2025-09-07T16-13-09Z}
MC_IMAGE=${MC_IMAGE:-ghcr.io/deckdumpster/mc:RELEASE.2025-08-13T08-35-41Z}
AWSCLI_IMAGE=${AWSCLI_IMAGE:-docker.io/amazon/aws-cli:2.37.3}

die() {
	echo "!! $*" >&2
	exit 1
}

# shellcheck source=deploy/store-lib.sh
. "${REPO_DIR}/deploy/store-lib.sh"
mtgc_store_load_config
mtgc_store_activate

# Unique per checkout: several worktrees run gates beside each other.
SUFFIX="${MTGC_TZ_SUFFIX:-$(printf '%s' "$REPO_DIR" | sha1sum | cut -c1-6)}"
NET=mtgctz-net-${SUFFIX}
MINIO_CTR=mtgctz-minio-${SUFFIX}
BUCKET=mtgctz-${SUFFIX}
MINIO_PORT=${MINIO_PORT:-$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1])')}

ROOT_AK=mtgctzroot
ROOT_SK=mtgctzsecret123
CAT_AK=mtgctzcatalog
CAT_SK=mtgctzcatalogsecret123
TEN_AK=mtgctztenant
TEN_SK=mtgctztenantsecret123
BLIND_AK=mtgctzblind
BLIND_SK=mtgctzblindsecret123

WORK=${WORK:-$(mktemp -d "${TMPDIR:-/tmp}/mtgctz.XXXXXX")}
mkdir -p "$WORK/minio" "$WORK/policies" "$WORK/conf"
chmod 777 "$WORK/minio" "$WORK/policies"

cleanup() {
	if [ -n "${KEEP:-}" ]; then
		echo "KEEP=1 — MinIO http://localhost:${MINIO_PORT} (${ROOT_AK}/${ROOT_SK}), bucket ${BUCKET}, work ${WORK}"
		echo "  tear down: podman rm -f ${MINIO_CTR}; podman network rm ${NET}"
		return
	fi
	podman rm -f "$MINIO_CTR" >/dev/null 2>&1 || true
	podman network rm "$NET" >/dev/null 2>&1 || true
	podman unshare rm -rf "$WORK" 2>/dev/null || rm -rf "$WORK" 2>/dev/null || true
}
trap cleanup EXIT

# mc as an arbitrary identity; the alias is always `x`, so the SAME command
# answers differently under a different credential.
mc_as() {
	local ak="$1" sk="$2"
	shift 2
	podman run --rm -i --network "$NET" \
		-v "$WORK/policies:/policies:ro,Z" \
		-e "MC_HOST_x=http://${ak}:${sk}@${MINIO_CTR}:9000" \
		"$MC_IMAGE" "$@"
}
mc_root() { mc_as "$ROOT_AK" "$ROOT_SK" "$@"; }

MINIO_URL="http://${MINIO_CTR}:9000"
aws_wrapper() { # aws_wrapper AK SK
	echo "podman run --rm --network ${NET} -e AWS_ACCESS_KEY_ID=$1 -e AWS_SECRET_ACCESS_KEY=$2 -e AWS_DEFAULT_REGION=us-west-2 ${AWSCLI_IMAGE}"
}

zone_script_as() {
	local ak="$1" sk="$2"
	shift 2
	MTGC_AWS="$(aws_wrapper "$ak" "$sk")" MTGC_CONFIG_DIR="${WORK}/conf" \
		bash "${REPO_DIR}/deploy/setup-tenant-zone.sh" \
		--bucket "$BUCKET" --endpoint "$MINIO_URL" "$@"
}
zone_script() { zone_script_as "$ROOT_AK" "$ROOT_SK" "$@"; }

# ---------------------------------------------------------------------------
echo "==> §0  Object store, and a catalog zone with real bytes in it"
# Deny assertions must fail because they are DENIED, never because the object is
# missing, so every prefix gets a real object placed by root.
podman network create "$NET" >/dev/null
podman run -d --name "$MINIO_CTR" --network "$NET" \
	-p "127.0.0.1:${MINIO_PORT}:9000" \
	-e MINIO_ROOT_USER="$ROOT_AK" -e MINIO_ROOT_PASSWORD="$ROOT_SK" \
	-v "$WORK/minio:/data:Z" "$MINIO_IMAGE" server /data >/dev/null

for _ in $(seq 1 120); do
	curl -sf -o /dev/null "http://localhost:${MINIO_PORT}/minio/health/live" && break
	sleep 0.25
done
curl -sf -o /dev/null "http://localhost:${MINIO_PORT}/minio/health/live" ||
	die "MinIO never became healthy on ${MINIO_PORT}"

mc_root mb "x/${BUCKET}" >/dev/null
RAW_KEY="raw/source=tcgcsv/dataset=groups/ingest_date=2026-10-14/run=01TEST/part-0000.json"
LAKE_KEY="lake/catalog/prices/metadata/v1.metadata.json"
printf '%s' '{"catalog":"a landed upstream response"}' | mc_root pipe "x/${BUCKET}/${RAW_KEY}" >/dev/null
printf '%s' '{"catalog":"an iceberg table metadata file"}' | mc_root pipe "x/${BUCKET}/${LAKE_KEY}" >/dev/null
echo "    bucket ${BUCKET}: catalog zone seeded under raw/ and lake/"

# ---------------------------------------------------------------------------
echo "==> §1  Retention applied by the real deploy/setup-tenant-zone.sh"
zone_script --apply >"${WORK}/apply.log" 2>&1 ||
	die "setup-tenant-zone.sh --apply failed: $(cat "${WORK}/apply.log")"
grep -q "expires after 90 days" "${WORK}/apply.log" ||
	die "--apply did not report the 90-day rule: $(cat "${WORK}/apply.log")"
zone_script --check >/dev/null 2>&1 || die "--check disagreed with the rule --apply had just written"
echo "    ok   tenant/ expires after 90 days, and the script verified its own write"

echo "==> §1b The script refuses rather than guessing a bucket"
RC=0
OUT=$(MTGC_CONFIG_DIR="${WORK}/conf" bash "${REPO_DIR}/deploy/setup-tenant-zone.sh" --check 2>&1) || RC=$?
[ "$RC" -ne 0 ] || die "the script accepted an unconfigured bucket"
case "$OUT" in *MTGC_LAKE_S3_BUCKET*) ;; *) die "refused without naming MTGC_LAKE_S3_BUCKET: ${OUT}" ;; esac
RC=0
OUT=$(MTGC_CONFIG_DIR="${WORK}/conf" bash "${REPO_DIR}/deploy/setup-tenant-zone.sh" --check \
	--bucket "$BUCKET" --backup-bucket "$BUCKET" 2>&1) || RC=$?
[ "$RC" -ne 0 ] || die "the script accepted a backup bucket"
case "$OUT" in *BACKUP*) ;; *) die "refused for the wrong reason: ${OUT}" ;; esac
echo "    ok   no bucket -> refuses; a backup bucket -> refuses"

# ---------------------------------------------------------------------------
echo "==> §2  Retention seen RED: ABSENT, FORBIDDEN and WRONG are three answers"
put_lifecycle() {
	podman run --rm --network "$NET" \
		-e AWS_ACCESS_KEY_ID="$ROOT_AK" -e AWS_SECRET_ACCESS_KEY="$ROOT_SK" -e AWS_DEFAULT_REGION=us-west-2 \
		"$AWSCLI_IMAGE" --endpoint-url "$MINIO_URL" s3api put-bucket-lifecycle-configuration \
		--bucket "$BUCKET" --lifecycle-configuration "$1" >/dev/null
}
delete_lifecycle() {
	podman run --rm --network "$NET" \
		-e AWS_ACCESS_KEY_ID="$ROOT_AK" -e AWS_SECRET_ACCESS_KEY="$ROOT_SK" -e AWS_DEFAULT_REGION=us-west-2 \
		"$AWSCLI_IMAGE" --endpoint-url "$MINIO_URL" s3api delete-bucket-lifecycle --bucket "$BUCKET" >/dev/null
}
expect_check_rc() { # expect_check_rc <want-rc> <phrase> <what>
	local want="$1" phrase="$2" what="$3" rc=0
	zone_script --check >"${WORK}/check.log" 2>&1 || rc=$?
	[ "$rc" -ne 0 ] || die "the retention check PASSED with ${what} — it is not checking anything"
	[ "$rc" -eq "$want" ] || die "the check answered ${rc} for ${what}, expected ${want}: $(cat "${WORK}/check.log")"
	grep -q "$phrase" "${WORK}/check.log" ||
		die "the check exited ${rc} for ${what} without saying '${phrase}': $(cat "${WORK}/check.log")"
	echo "    red  ${what} -> exit ${rc}"
}

put_lifecycle '{"Rules":[{"ID":"whole-bucket","Status":"Enabled","Filter":{"Prefix":""},"Expiration":{"Days":90}}]}'
expect_check_rc 1 "spans the whole bucket" "a whole-bucket rule (it would expire the catalog)"
put_lifecycle '{"Rules":[{"ID":"too-long","Status":"Enabled","Filter":{"Prefix":"tenant/"},"Expiration":{"Days":365}}]}'
expect_check_rc 1 "not 90" "365-day retention on tenant/"
put_lifecycle '{"Rules":[{"ID":"tenant","Status":"Enabled","Filter":{"Prefix":"tenant/"},"Expiration":{"Days":90}},{"ID":"tidy-raw","Status":"Enabled","Filter":{"Prefix":"raw/"},"Expiration":{"Days":30}}]}'
expect_check_rc 1 "reaches the catalog zone" "a second rule expiring raw/"
delete_lifecycle
expect_check_rc 3 "ABSENT" "no lifecycle configuration at all"

zone_script --apply >/dev/null 2>&1 || die "re-applying the correct rule failed"
zone_script --check >/dev/null 2>&1 || die "the check did not go green again"
echo "    ok   and green again once the correct rule is restored"

echo "==> §2b The same correct rule, read by a credential that may not look"
cat >"${WORK}/policies/blind.json" <<EOP
{"Version":"2012-10-17","Statement":[{"Effect":"Allow",
"Action":["s3:GetObject","s3:ListBucket"],
"Resource":["arn:aws:s3:::${BUCKET}","arn:aws:s3:::${BUCKET}/*"]}]}
EOP
policy_install() { # policy_install NAME FILE
	mc_root admin policy create x "$1" "/policies/$2" >/dev/null 2>&1 ||
		mc_root admin policy add x "$1" "/policies/$2" >/dev/null 2>&1 ||
		die "could not install the $1 policy"
}
policy_attach() { mc_root admin policy attach x "$1" --user "$2" >/dev/null 2>&1 || die "could not attach $1 to $2"; }
# A detach that quietly did nothing would make §6's red run come out green and be
# misread as "the check is broken", so it fails loudly.
policy_detach() { mc_root admin policy detach x "$1" --user "$2" >/dev/null 2>&1 || die "could not detach $1 from $2"; }

mc_root admin user add x "$BLIND_AK" "$BLIND_SK" >/dev/null
policy_install mtgctz-blind blind.json
policy_attach mtgctz-blind "$BLIND_AK"
mc_as "$BLIND_AK" "$BLIND_SK" ls "x/${BUCKET}/raw/" >/dev/null 2>&1 ||
	die "the lifecycle-blind credential cannot reach the bucket at all — it proves nothing"
BLIND_RC=0
zone_script_as "$BLIND_AK" "$BLIND_SK" --check >"${WORK}/blind.log" 2>&1 || BLIND_RC=$?
[ "$BLIND_RC" -eq 4 ] || die "a credential that may not READ the lifecycle answered ${BLIND_RC}; expected 4: $(cat "${WORK}/blind.log")"
grep -q "CANNOT VERIFY" "${WORK}/blind.log" || die "a denied read did not say CANNOT VERIFY"
grep -q "s3:GetLifecycleConfiguration" "${WORK}/blind.log" || die "a denied read did not name the missing permission"
if grep -q "ABSENT" "${WORK}/blind.log"; then die "a DENIED read was reported as ABSENT: $(cat "${WORK}/blind.log")"; fi
echo "    red  a credential without s3:GetLifecycleConfiguration -> exit 4, not 3"
zone_script --check >/dev/null 2>&1 || die "the correct rule did not survive the forbidden probe"
echo "    ok   and the rule it could not see is still applied, and still correct"

# ---------------------------------------------------------------------------
echo "==> §3  Two identities, from the rendered policy documents"
zone_script --render --out "${WORK}/policies" --litestream-bucket mtgctz-litestream-unused >/dev/null || die "--render failed"
[ -s "${WORK}/policies/catalog-credentials.json" ] || die "no rendered catalog policy"
[ -s "${WORK}/policies/tenant-credentials.json" ] || die "no rendered tenant policy"
if grep -q "{{" "${WORK}/policies/catalog-credentials.json" "${WORK}/policies/tenant-credentials.json"; then
	die "a rendered policy still carries a placeholder"
fi
grep -q "arn:aws:s3:::${BUCKET}/tenant/\*" "${WORK}/policies/catalog-credentials.json" ||
	die "the rendered catalog policy does not name this bucket's tenant prefix"

mc_root admin user add x "$CAT_AK" "$CAT_SK" >/dev/null
mc_root admin user add x "$TEN_AK" "$TEN_SK" >/dev/null
policy_install mtgctz-catalog catalog-credentials.json
policy_install mtgctz-tenant tenant-credentials.json
policy_attach mtgctz-catalog "$CAT_AK"
policy_attach mtgctz-tenant "$TEN_AK"
echo "    ok   ${CAT_AK} and ${TEN_AK} carry the two documents, verbatim"

can_get() { mc_as "$1" "$2" cat "x/${BUCKET}/$3" >/dev/null 2>&1; }
can_put() { printf 'governance probe' | mc_as "$1" "$2" pipe "x/${BUCKET}/$3" >/dev/null 2>&1; }
can_list() { mc_as "$1" "$2" ls "x/${BUCKET}/$3" >/dev/null 2>&1; }
can_rm() { mc_as "$1" "$2" rm --force "x/${BUCKET}/$3" >/dev/null 2>&1; }

PROBE_KEY="tenant/database_id=01TESTPROBE0000000000TZTZ/dataset=holdings/as_of=2026-10-14/part-seq-1-1.parquet.enc"

# The isolation claims are functions so §6 re-runs exactly these against a
# deliberately broken configuration.  They print what failed and return non-zero.
catalog_cannot_reach_tenant() {
	local bad=0
	if can_get "$CAT_AK" "$CAT_SK" "$PROBE_KEY"; then echo "   !! catalog credentials READ tenant/" >&2; bad=1; fi
	if can_list "$CAT_AK" "$CAT_SK" "tenant/"; then echo "   !! catalog credentials LISTED tenant/" >&2; bad=1; fi
	if can_put "$CAT_AK" "$CAT_SK" "tenant/database_id=01TESTPROBE0000000000TZTZ/intrusion"; then
		echo "   !! catalog credentials WROTE into tenant/" >&2; bad=1
	fi
	return "$bad"
}
tenant_cannot_reach_catalog() {
	local bad=0
	if can_get "$TEN_AK" "$TEN_SK" "$RAW_KEY"; then echo "   !! tenant credentials READ raw/" >&2; bad=1; fi
	if can_get "$TEN_AK" "$TEN_SK" "$LAKE_KEY"; then echo "   !! tenant credentials READ lake/" >&2; bad=1; fi
	if can_list "$TEN_AK" "$TEN_SK" "raw/"; then echo "   !! tenant credentials LISTED raw/" >&2; bad=1; fi
	if can_put "$TEN_AK" "$TEN_SK" "raw/intrusion"; then echo "   !! tenant credentials WROTE into raw/" >&2; bad=1; fi
	return "$bad"
}
catalog_zone_is_append_only() {
	local bad=0
	if can_rm "$CAT_AK" "$CAT_SK" "$RAW_KEY"; then echo "   !! catalog credentials DELETED from raw/" >&2; bad=1; fi
	return "$bad"
}

# ---------------------------------------------------------------------------
echo "==> §4  Each identity CAN reach its own zone"
can_get "$CAT_AK" "$CAT_SK" "$RAW_KEY" || die "catalog credentials cannot read their own raw/ object — the policy is too narrow"
can_get "$CAT_AK" "$CAT_SK" "$LAKE_KEY" || die "catalog credentials cannot read their own lake/ object"
can_list "$CAT_AK" "$CAT_SK" "raw/" || die "catalog credentials cannot list raw/"
can_put "$CAT_AK" "$CAT_SK" "raw/_probe" || die "catalog credentials cannot append to raw/"
can_put "$TEN_AK" "$TEN_SK" "$PROBE_KEY" || die "tenant credentials cannot write their own zone"
can_get "$TEN_AK" "$TEN_SK" "$PROBE_KEY" || die "tenant credentials cannot read back what they wrote"
[[ "$(mc_as "$TEN_AK" "$TEN_SK" cat "x/${BUCKET}/${PROBE_KEY}")" == "governance probe" ]] || die "wrong probe content"
can_list "$TEN_AK" "$TEN_SK" "tenant/" || die "tenant credentials cannot list tenant/"
echo "    ok   catalog reads and appends raw/ + lake/; tenant reads, writes and lists tenant/"

echo "==> §5  THE GATE, both directions, against the correct configuration"
catalog_cannot_reach_tenant || die "catalog credentials reached the tenant zone"
tenant_cannot_reach_catalog || die "tenant credentials reached the catalog zone"
catalog_zone_is_append_only || die "the catalog zone is not append-only"
echo "    ok   neither can read, list or write the other's zone; raw/ cannot be deleted from"

# ---------------------------------------------------------------------------
echo "==> §6  THE GATE SEEN RED: break the boundary, the SAME assertions must fail"
WIDE='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"s3:*","Resource":["arn:aws:s3:::'"${BUCKET}"'","arn:aws:s3:::'"${BUCKET}"'/*"]}]}'
printf '%s' "$WIDE" >"${WORK}/policies/wide.json"
policy_install mtgctz-wide wide.json

expect_red() {
	local what="$1" fn="$2"
	if "$fn" 2>/dev/null; then
		die "${what}: the check still PASSED against a credential that can reach the whole bucket — it is not checking anything"
	fi
	echo "    red  ${what} replaced by a whole-bucket grant -> the check fails, as it must"
}

policy_detach mtgctz-catalog "$CAT_AK"
policy_attach mtgctz-wide "$CAT_AK"
expect_red "catalog credentials (isolation)" catalog_cannot_reach_tenant
expect_red "catalog credentials (append-only)" catalog_zone_is_append_only
policy_detach mtgctz-wide "$CAT_AK"
policy_attach mtgctz-catalog "$CAT_AK"
catalog_cannot_reach_tenant || die "restoring the catalog policy did not restore the boundary"
echo "    ok   and green again once the correct policy is restored"

# The red run just deleted raw/; put the seeded object back for what follows.
printf '%s' '{"catalog":"a landed upstream response"}' | mc_root pipe "x/${BUCKET}/${RAW_KEY}" >/dev/null

policy_detach mtgctz-tenant "$TEN_AK"
policy_attach mtgctz-wide "$TEN_AK"
expect_red "tenant credentials" tenant_cannot_reach_catalog
policy_detach mtgctz-wide "$TEN_AK"
policy_attach mtgctz-tenant "$TEN_AK"
tenant_cannot_reach_catalog || die "restoring the tenant policy did not restore the boundary"
echo "    ok   and green again once the correct policy is restored"

echo "==> §6b The explicit Deny statements are load-bearing, not decoration"
# An explicit Deny beats any Allow, so a broader grant made somewhere else cannot
# silently widen either zone.
policy_attach mtgctz-wide "$CAT_AK"
catalog_cannot_reach_tenant || die "a whole-bucket grant ALONGSIDE the catalog policy opened the tenant zone"
policy_detach mtgctz-wide "$CAT_AK"
policy_attach mtgctz-wide "$TEN_AK"
tenant_cannot_reach_catalog || die "a whole-bucket grant ALONGSIDE the tenant policy opened the catalog zone"
policy_detach mtgctz-wide "$TEN_AK"
echo "    ok   a whole-bucket grant added BESIDE either policy still cannot cross"

# ---------------------------------------------------------------------------
echo "==> §7  Clean up the probes; the zone is EMPTY and the catalog untouched"
can_rm "$TEN_AK" "$TEN_SK" "tenant/" >/dev/null 2>&1 || true
mc_root rm --recursive --force "x/${BUCKET}/tenant/" >/dev/null 2>&1 || true
mc_root rm --force "x/${BUCKET}/raw/_probe" "x/${BUCKET}/raw/intrusion" >/dev/null 2>&1 || true
# Listed from the bucket root and checked against a sentinel before it is
# believed: "nothing is left" is also what an mc that died reports.
LISTING="$(mc_root ls --recursive "x/${BUCKET}/")"
grep -q ' raw/' <<<"$LISTING" || die "the bucket listing did not show the seeded raw/ object — it cannot be trusted"
REMAINING=$(grep -c ' tenant/' <<<"$LISTING" || true)
[ "$REMAINING" -eq 0 ] || die "${REMAINING} object(s) remain under tenant/"
CATALOG_OBJECTS=$(grep -c ' raw/\| lake/' <<<"$LISTING" || true)
[ "$CATALOG_OBJECTS" -eq 2 ] || die "the catalog zone holds ${CATALOG_OBJECTS} objects, expected the 2 seeded"
echo "    ok   tenant/ holds nothing; the catalog's 2 seeded objects are untouched"

echo ""
echo "==> tests/lake/tenant_zone.sh PASSED"
