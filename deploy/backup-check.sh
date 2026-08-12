#!/usr/bin/env bash
#
# Backup-freshness dead-man's switch for an MTGC instance (de-d8v).
#
# Modelled on pokedumpster:deploy/backup-check.sh, which exists because of a real
# Jun 2026 key rotation: the Litestream sidecar showed systemd `active` while
# error-looping on AccessDenied and replicating nothing. The lesson, quoted:
#
#     liveness is NOT freshness
#
# A nightly cron has the same failure shape and a worse one besides. backup.sh
# can exit 0 having uploaded nothing — bad credentials, a full disk, an empty
# tarball, a silently truncated dump — and cron logs success every night forever.
# The first sign would be needing a restore. This bucket already carries the
# evidence: 2026-08-08 and 2026-08-11 have no object at all, and nothing said so.
#
# So this script does not ask whether the job ran. It asks S3 what is actually
# there:
#   1. List the instance's backup prefix (read-only, s3:ListBucket only).
#   2. If the list itself FAILS -> STALE. "We could not ask" and "the answer is
#      fine" must never be the same outcome.
#   3. No objects at all -> STALE.
#   4. Newest object older than the threshold -> STALE.
#   5. Newest object below an absolute byte floor -> STALE. A 0-byte or
#      implausibly small object is a silent failure, not a backup.
#   6. Newest object materially SMALLER than the one before it -> STALE. A
#      truncated dump still has a plausible mtime and a plausible-looking size;
#      only the comparison catches it.
#   7. All of the above pass -> ping the off-box monitor (healthchecks.io).
#
# The ping happens HERE and only on a verified-fresh result. Pinging from inside
# backup.sh would prove the job ran, which is the thing that is already not in
# question. And because the monitor lives off the box, a dead checker, a dead
# box or a disabled timer also stops the pings and trips the alert.
#
# ── NO CHECK MAY PASS BY SKIPPING ───────────────────────────────────────────
# There is no configuration of this script that makes it exit 0 without asking
# S3. An unset monitor URL disables the PING and nothing else: freshness is
# still verified and a stale backup still fails, it just cannot arm the off-box
# dead-man. A missing bucket is a failure outright — an instance with no
# off-site target has no backup to be fresh.
#
# READ-ONLY BY CONSTRUCTION: the only AWS call below is `s3api list-objects-v2`.
# A checker that could damage what it watches is a liability; the minimal policy
# is s3:ListBucket on the bucket, and nothing else. See deploy/README.md.
#
# Usage: backup-check.sh [instance]        (default: prod)
set -euo pipefail

INSTANCE="${1:-prod}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# The config directory. Production never sets MTGC_CONFIG_DIR; only tests point
# it elsewhere, so a gate can exercise the shipped script without reading — or
# depending on — the operator's real credentials.
CONF_DIR="${MTGC_CONFIG_DIR:-${HOME}/.config/mtgc}"

# Host-wide alert channel first, then the instance's own env (the same file the
# nightly cron sources), so per-instance settings win.
[ -f "${CONF_DIR}/alerts.env" ]         && { set -a; . "${CONF_DIR}/alerts.env";         set +a; }
[ -f "${CONF_DIR}/${INSTANCE}.env" ]    && { set -a; . "${CONF_DIR}/${INSTANCE}.env";    set +a; }

BUCKET="${MTGC_BACKUP_S3_BUCKET:-}"
PREFIX="${MTGC_BACKUP_S3_PREFIX:-mtgc-${INSTANCE}/}"
PING="${MTGC_BACKUP_PING_URL:-}"

# Backups are nightly at 03:00 and take ~7 minutes to upload. The threshold has
# to clear one full interval plus margin so a single late night is not an alarm;
# 30h means a genuinely missed night is red within 6h of crossing it.
MAX_AGE_HOURS="${MTGC_BACKUP_MAX_AGE_HOURS:-30}"
# Absolute floor. The real tarball is ~3 GB; anything under a megabyte is not a
# backup by any reading, whatever produced it.
MIN_BYTES="${MTGC_BACKUP_MIN_BYTES:-1048576}"
# The tarball grows monotonically (~13 MB/night on prod). A drop of this much
# against the previous backup means content went missing, not that the data did.
MAX_SHRINK_PCT="${MTGC_BACKUP_MAX_SHRINK_PCT:-10}"

# Only tests set this (a local MinIO); production talks to real S3.
ENDPOINT_ARGS=()
[ -n "${MTGC_BACKUP_S3_ENDPOINT:-}" ] && ENDPOINT_ARGS=(--endpoint-url "${MTGC_BACKUP_S3_ENDPOINT}")

# --- Failure path -----------------------------------------------------------
#
# Trip the off-box dead-man immediately rather than waiting out the monitor's
# grace window, then push the detail. Only if there is a monitor to trip: an
# unarmed channel changes what this failure can NOTIFY, never whether it is a
# failure, so the exit status belongs to the verdict alone.
stale() {
    local reason="$1"
    echo "backup-check: STALE — ${reason}" >&2
    if [ -n "$PING" ]; then
        curl -fsS -m 10 "${PING}/fail" >/dev/null 2>&1 || true
    fi
    "${SCRIPT_DIR}/alert.sh" "MTGC backup STALE (${INSTANCE})" \
        "S3 freshness check failed: ${reason}" || true
    exit 1
}

# --- Configuration ----------------------------------------------------------

# Not a skip. An instance with no off-site bucket has nothing off-box to be
# fresh, and reporting that as OK is the defect this whole script exists to
# remove.
if [ -z "$BUCKET" ]; then
    echo "backup-check: FAILED — MTGC_BACKUP_S3_BUCKET is unset for instance '${INSTANCE}';" \
         "there is no off-site backup to verify. Set it in ${CONF_DIR}/${INSTANCE}.env." >&2
    exit 1
fi

# The verification below runs either way; this only says which half is armed.
if [ -z "$PING" ]; then
    echo "backup-check: MTGC_BACKUP_PING_URL unset — verifying freshness anyway;" \
         "the off-box dead-man's switch is NOT armed (instance: ${INSTANCE})." \
         "To arm it: put the healthchecks.io ping URL in ${CONF_DIR}/${INSTANCE}.env."
fi

command -v aws >/dev/null 2>&1 \
    || stale "the 'aws' CLI is not installed — the backup target cannot be queried at all"

# --- Ask S3 what is actually there ------------------------------------------
#
# Every object's timestamp, size and key. Deliberately NOT `--query
# 'sort_by(...)[-1]'`: the CLI paginates automatically and applies --query per
# page, so a bucket that outgrows one page would silently return the newest
# object OF EACH PAGE and the sort would be meaningless. A plain projection
# concatenates correctly, and the sorting happens here.
LISTING="$(aws s3api list-objects-v2 \
    "${ENDPOINT_ARGS[@]}" \
    --bucket "$BUCKET" \
    --prefix "$PREFIX" \
    --query 'Contents[].[LastModified,Size,Key]' \
    --output text 2>&1)" \
    || stale "could not list s3://${BUCKET}/${PREFIX} (credentials, network or bucket policy): $(printf '%s' "$LISTING" | tail -n1)"

# LastModified is RFC3339 with a fixed +00:00 offset, so lexicographic order is
# chronological order.
LISTING="$(printf '%s\n' "$LISTING" | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}T' | sort || true)"

if [ -z "$LISTING" ]; then
    stale "s3://${BUCKET}/${PREFIX} contains NO objects — this instance is not backed up"
fi

NEWEST_LINE="$(printf '%s\n' "$LISTING" | tail -n1)"
PREV_LINE="$(printf '%s\n' "$LISTING" | tail -n2 | head -n1)"

read -r NEWEST_TS NEWEST_BYTES NEWEST_KEY <<<"$NEWEST_LINE"

NEWEST_EPOCH="$(date -d "$NEWEST_TS" +%s 2>/dev/null)" \
    || stale "could not parse the newest object's timestamp: ${NEWEST_TS}"
AGE_HOURS=$(( ( $(date +%s) - NEWEST_EPOCH ) / 3600 ))

# --- Freshness --------------------------------------------------------------

if [ "$AGE_HOURS" -gt "$MAX_AGE_HOURS" ]; then
    stale "newest backup ${NEWEST_KEY} is ${AGE_HOURS}h old (> ${MAX_AGE_HOURS}h threshold)"
fi

# --- Size: an absolute floor, then the comparison ---------------------------

if [ "$NEWEST_BYTES" -lt "$MIN_BYTES" ]; then
    stale "newest backup ${NEWEST_KEY} is only ${NEWEST_BYTES} bytes (< ${MIN_BYTES} floor) — not a backup"
fi

if [ "$NEWEST_LINE" != "$PREV_LINE" ]; then
    read -r _ PREV_BYTES PREV_KEY <<<"$PREV_LINE"
    # Integer arithmetic, so compute the allowed floor rather than a percentage
    # of the observed drop.
    MIN_ALLOWED=$(( PREV_BYTES * (100 - MAX_SHRINK_PCT) / 100 ))
    if [ "$NEWEST_BYTES" -lt "$MIN_ALLOWED" ]; then
        stale "newest backup ${NEWEST_KEY} is ${NEWEST_BYTES} bytes, down from ${PREV_BYTES} in ${PREV_KEY} (> ${MAX_SHRINK_PCT}% smaller) — content is missing from it"
    fi
    SIZE_NOTE="$(( NEWEST_BYTES / 1048576 )) MiB, previous $(( PREV_BYTES / 1048576 )) MiB"
else
    # One object total: nothing to compare against yet. Said out loud rather
    # than passed over, because "the shrink check ran" and "there was only ever
    # one backup" look identical in a green log otherwise.
    SIZE_NOTE="$(( NEWEST_BYTES / 1048576 )) MiB, no previous backup to compare against"
fi

# --- Fresh: ping the monitor ------------------------------------------------

echo "backup-check: OK — ${NEWEST_KEY} is ${AGE_HOURS}h old (<= ${MAX_AGE_HOURS}h), ${SIZE_NOTE}"
if [ -z "$PING" ]; then
    echo "backup-check: no monitor to ping — a dead box or a disabled timer would go unnoticed"
else
    curl -fsS -m 10 "$PING" >/dev/null 2>&1 \
        || echo "backup-check: WARNING — monitor ping failed (will retry next run)" >&2
fi
