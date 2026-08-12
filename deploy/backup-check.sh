#!/usr/bin/env bash
#
# Backup-freshness dead-man's switch (de-d8v).
#
# backup.sh runs nightly and syncs tarballs to S3. It can exit 0 having uploaded
# nothing — bad credentials, a full disk, an empty tarball, a truncated dump —
# and the cron log will read "success" every night forever. The lesson is
# pokedumpster's, learned during a Jun 2026 key rotation where a replicator
# showed systemd `active` while error-looping on AccessDenied:
#
#     liveness is NOT freshness
#
# So this checker asks S3 what actually landed, never the local job:
#   1. List s3://<bucket>/mtgc-<instance>/daily/ (read-only). backup.sh writes a
#      new object there every night; weekly/ and monthly/ are promotion tiers and
#      go long stretches untouched, so daily/ is the only tier whose age means
#      anything.
#   2. Listing FAILS (broken creds, network, missing bucket) -> NOT fresh. This
#      is the failure that killed pokedumpster's replication: the same creds the
#      uploader uses are the ones being exercised here.
#   3. Newest object older than the threshold -> NOT fresh.
#   4. Newest object implausibly small, in absolute terms or against the previous
#      night's -> NOT fresh. A 0-byte object is a silent failure, not a backup.
#   5. Fresh -> ping the off-box monitor (it expects a ping every run; a miss
#      alerts). Stale -> ping <url>/fail to trip it immediately, plus a Pushover
#      push with the detail.
#
# Because the monitor lives OFF the box, a dead checker / dead box / disabled
# timer ALSO stops the pings and trips the alert. The Pushover push is the fast,
# detailed signal while the box is up; the monitor is the backstop for box-down.
#
# Read-only by design: it lists objects and reads their metadata. It never puts
# or deletes, so it cannot damage the thing it is watching, and read-only
# credentials are enough.
#
# Silent unless a bucket is configured: MTGC_BACKUP_S3_BUCKET unset means the
# instance has no off-site backup to verify, so there is nothing to check and
# dev/test boxes are unaffected. MTGC_BACKUP_PING_URL is independently optional —
# unset just means no monitor to ping; the freshness assertions still run and
# still alert, which is what you want on a box whose backups are real but whose
# monitor is not wired up yet.
#
# Usage: backup-check.sh <instance>
set -euo pipefail
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

INSTANCE="${1:?usage: backup-check.sh <instance>}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Host-wide Pushover creds, then the per-instance env (bucket, AWS profile, ping
# URL, thresholds). The instance env wins — it is the same file backup.sh's cron
# entry sources.
[ -f "${HOME}/.config/mtgc/alerts.env" ]        && { set -a; . "${HOME}/.config/mtgc/alerts.env";        set +a; }
[ -f "${HOME}/.config/mtgc/${INSTANCE}.env" ]   && { set -a; . "${HOME}/.config/mtgc/${INSTANCE}.env";   set +a; }

BUCKET="${MTGC_BACKUP_S3_BUCKET:-}"
PING="${MTGC_BACKUP_PING_URL:-}"
# The backup runs once a day at 03:00 and takes minutes to build and sync a
# multi-GB tarball. 36h clears a full interval plus the run itself plus margin,
# so one late night doesn't false-alarm but two consecutive misses do.
MAX_AGE_HOURS="${MTGC_BACKUP_MAX_AGE_HOURS:-36}"
# The dataset grows monotonically (~13 MB/night at present), so any drop is
# suspicious; 50% is the point past which it is not explicable as churn.
MIN_SIZE_PCT="${MTGC_BACKUP_MIN_SIZE_PCT:-50}"
# Absolute floor, for the case where there is no previous object to compare
# against. A real tarball is gigabytes; anything under 1 MiB is a failed dump.
MIN_SIZE_BYTES="${MTGC_BACKUP_MIN_SIZE_BYTES:-1048576}"

PREFIX="mtgc-${INSTANCE}/daily/"

# No off-site backup configured -> nothing to verify. Keeps dev/test silent.
if [ -z "$BUCKET" ]; then
    echo "backup-check: MTGC_BACKUP_S3_BUCKET unset — skipping (instance: ${INSTANCE})"
    exit 0
fi

stale() {
    local reason="$1"
    echo "backup-check: STALE — ${reason}" >&2
    # Trip the off-box dead-man immediately rather than waiting out its grace
    # window on a missed ping.
    [ -n "$PING" ] && { curl -fsS -m 10 "${PING}/fail" >/dev/null 2>&1 || true; }
    "${SCRIPT_DIR}/alert.sh" "MTGC backup STALE (${INSTANCE})" \
        "S3 freshness check failed for s3://${BUCKET}/${PREFIX} — ${reason}" || true
    exit 1
}

command -v aws >/dev/null 2>&1 || stale "aws CLI not found on PATH"

# --- List the daily tier (read-only) --------------------------------------
# list-objects-v2 is a pure read. Broken creds surface here exactly as they
# would for the uploader, which is the whole point.
LIST_OUT="$(aws s3api list-objects-v2 \
    --bucket "$BUCKET" \
    --prefix "$PREFIX" \
    --query 'Contents[].[LastModified,Size,Key]' \
    --output text 2>&1)" \
    || stale "S3 list failed (creds/network/bucket): $(printf '%s' "$LIST_OUT" | tail -n1)"

# No objects at all: --output text renders an absent Contents as "None".
OBJECTS="$(printf '%s\n' "$LIST_OUT" | grep -v '^None$' | grep -v '^$' || true)"
[ -n "$OBJECTS" ] || stale "no objects under s3://${BUCKET}/${PREFIX}"

# LastModified is RFC3339 Zulu, so lexicographic sort == chronological.
SORTED="$(printf '%s\n' "$OBJECTS" | sort)"
NEWEST_LINE="$(printf '%s\n' "$SORTED" | tail -n1)"
PREV_LINE="$(printf '%s\n' "$SORTED" | tail -n2 | head -n1)"

NEWEST_TS="$(printf '%s' "$NEWEST_LINE" | cut -f1)"
NEWEST_SIZE="$(printf '%s' "$NEWEST_LINE" | cut -f2)"
NEWEST_KEY="$(printf '%s' "$NEWEST_LINE" | cut -f3)"

NEWEST_EPOCH="$(date -d "$NEWEST_TS" +%s 2>/dev/null)" || stale "could not parse LastModified: ${NEWEST_TS}"
AGE_H=$(( ( $(date +%s) - NEWEST_EPOCH ) / 3600 ))

# --- Age ------------------------------------------------------------------

if [ "$AGE_H" -gt "$MAX_AGE_HOURS" ]; then
    stale "newest object ${NEWEST_KEY} is ${AGE_H}h old (> ${MAX_AGE_HOURS}h threshold)"
fi

# --- Size -----------------------------------------------------------------

if [ "$NEWEST_SIZE" -lt "$MIN_SIZE_BYTES" ]; then
    stale "newest object ${NEWEST_KEY} is ${NEWEST_SIZE} bytes (< ${MIN_SIZE_BYTES} byte floor)"
fi

if [ "$NEWEST_LINE" != "$PREV_LINE" ]; then
    PREV_SIZE="$(printf '%s' "$PREV_LINE" | cut -f2)"
    PREV_KEY="$(printf '%s' "$PREV_LINE" | cut -f3)"
    # Integer percentage of the previous night's size. PREV_SIZE cleared the
    # same floor when it was the newest, so it is never 0 here in practice —
    # but a 0 would divide, so guard it.
    if [ "$PREV_SIZE" -gt 0 ]; then
        SIZE_PCT=$(( NEWEST_SIZE * 100 / PREV_SIZE ))
        if [ "$SIZE_PCT" -lt "$MIN_SIZE_PCT" ]; then
            stale "newest object ${NEWEST_KEY} is ${NEWEST_SIZE} bytes, ${SIZE_PCT}% of the previous ${PREV_KEY} (${PREV_SIZE} bytes) — below the ${MIN_SIZE_PCT}% floor"
        fi
    fi
fi

# --- Fresh: ping the monitor ----------------------------------------------

echo "backup-check: OK — ${NEWEST_KEY} is ${AGE_H}h old (<= ${MAX_AGE_HOURS}h), ${NEWEST_SIZE} bytes"
if [ -n "$PING" ]; then
    curl -fsS -m 10 "$PING" >/dev/null 2>&1 \
        || echo "backup-check: WARNING — monitor ping failed (will retry next run)" >&2
else
    echo "backup-check: MTGC_BACKUP_PING_URL unset — no monitor to ping"
fi
