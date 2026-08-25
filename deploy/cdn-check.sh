#!/usr/bin/env bash
#
# Post-deploy check that traverses the actual CDN path (de-dai).
#
# THE DEFECT THIS EXISTS TO REMOVE. On 2026-08-25 six commits deployed and the
# public site showed none of them for a day. Every check anyone ran that evening
# passed: deploy.sh's health check hit https://localhost:<port>, the LAN address
# served the new pages, the container was up, the git checkout was current. The
# only thing that was wrong was the one hop nobody measured — Cloudflare, which
# held each document for 24h because the origin said `public, max-age=86400`
# with no validator to revalidate against.
#
#     A deploy check that does not traverse the CDN is not a deploy check.
#
# So the load-bearing assertion here is ETAG EQUALITY BETWEEN THE EDGE AND THE
# ORIGIN. Asking the edge whether its own headers look sane would have passed
# that evening too: the headers Cloudflare was serving were internally
# consistent, they just described a day-old page. Only comparing the two sides
# distinguishes "the edge is serving what we deployed" from "the edge is serving
# something, plausibly".
#
# What it verifies, in order:
#   1. The origin answers and carries an ETag.
#   2. The public URL answers through Cloudflare and carries an ETag.
#   3. The two ETags are the same document  <-- the one that would have caught it
#   4. The public Cache-Control has no multi-hour max-age.
#   5. A conditional re-request through the edge returns 304.
#   6. The edge negotiates gzip.
#
# NO CHECK MAY PASS BY SKIPPING. There is no flag, no unset variable and no
# environment in which this exits 0 without having asked both sides and compared
# them. A Cloudflare Access interstitial is diagnosed BY NAME rather than being
# allowed to surface as a confusing ETag mismatch, because a wrong diagnosis
# that is trusted costs more than no diagnosis at all.
#
# Usage: cdn-check.sh [--url URL] [--origin URL] [--path PATH]
#
#   --url     public URL, through Cloudflare   (default https://magic.dumpster.cards)
#   --origin  origin URL, on the deploy box    (default https://localhost:8081)
#   --path    document path to compare         (default /)
#
# Behind Cloudflare Access, set CF_ACCESS_CLIENT_ID / CF_ACCESS_CLIENT_SECRET to
# a service token; without one the public request is answered by the Access
# login page and this script says so.
set -uo pipefail

PUBLIC_URL="${MTGC_PUBLIC_URL:-https://magic.dumpster.cards}"
ORIGIN_URL="${MTGC_ORIGIN_URL:-https://localhost:8081}"
DOC_PATH="/"

while [ $# -gt 0 ]; do
    case "$1" in
        --url)    PUBLIC_URL="$2"; shift 2 ;;
        --origin) ORIGIN_URL="$2"; shift 2 ;;
        --path)   DOC_PATH="$2";   shift 2 ;;
        *) echo "cdn-check: unknown argument '$1'" >&2; exit 2 ;;
    esac
done

PUBLIC_URL="${PUBLIC_URL%/}"
ORIGIN_URL="${ORIGIN_URL%/}"

ACCESS_ARGS=()
if [ -n "${CF_ACCESS_CLIENT_ID:-}" ] && [ -n "${CF_ACCESS_CLIENT_SECRET:-}" ]; then
    ACCESS_ARGS=(-H "CF-Access-Client-Id: ${CF_ACCESS_CLIENT_ID}"
                 -H "CF-Access-Client-Secret: ${CF_ACCESS_CLIENT_SECRET}")
fi

fail() {
    echo "cdn-check: FAILED — $*" >&2
    exit 1
}

# Response headers only, lower-cased names so the greps below are not at the
# mercy of which hop last rewrote the casing. `-k` covers the origin's
# self-signed cert on 8081; the public side goes through a real certificate and
# is unaffected by it.
headers_of() {
    curl -sS -k -m 20 -o /dev/null -D - "$@" 2>&1 \
        | tr -d '\r' | awk '{ n=index($0,":"); if (n) printf "%s%s\n", tolower(substr($0,1,n)), substr($0,n+1); else print tolower($0) }'
}

# curl writes its own diagnostics into the same stream, so a connection that
# never happened has a message in it. Surfacing that beats reporting the absence
# of a status line, which describes the symptom and not the cause.
transport_error() { printf '%s\n' "$1" | grep -iv '^http/' | grep -i 'curl:' | tail -n1; }

header_value() { printf '%s\n' "$1" | grep -i "^$2:" | tail -n1 | sed "s/^$2: *//i"; }
status_of()    { printf '%s\n' "$1" | grep -E '^http/' | tail -n1 | awk '{print $2}'; }

# Cloudflare Access answers an unauthenticated request with a redirect to the
# team login domain. Left undiagnosed that becomes "the ETags differ", which
# sends the reader to the deploy and the cache — neither of which is wrong.
assert_not_access_wall() {
    local dump="$1"
    if printf '%s\n' "$dump" | grep -qi 'cloudflareaccess\.com'; then
        fail "the public URL was answered by the Cloudflare Access login page, not by the app.
    Nothing about the deploy has been verified. Set CF_ACCESS_CLIENT_ID and
    CF_ACCESS_CLIENT_SECRET to an Access service token and run this again."
    fi
}

# ── 1. The origin ───────────────────────────────────────────────────────────
#
# `Accept-Encoding: identity` on BOTH sides. The two must be compared as the
# same representation: the server mints a distinct ETag per encoding on purpose,
# and Cloudflare re-compresses on its own schedule, so letting either side pick
# would make the comparison a coin toss.
ORIGIN_DUMP="$(headers_of -H 'Accept-Encoding: identity' "${ORIGIN_URL}${DOC_PATH}")"
ORIGIN_STATUS="$(status_of "$ORIGIN_DUMP")"
[ "$ORIGIN_STATUS" = "200" ] \
    || fail "the origin ${ORIGIN_URL}${DOC_PATH} answered '${ORIGIN_STATUS:-nothing}', not 200.
    $(transport_error "$ORIGIN_DUMP")
    The CDN cannot be serving a current deploy of something that is not running."

ORIGIN_ETAG="$(header_value "$ORIGIN_DUMP" etag)"
[ -n "$ORIGIN_ETAG" ] \
    || fail "the origin served no ETag. Without a validator the edge has nothing to
    revalidate against, which is exactly the condition that made deploys invisible."

# ── 2. The edge ─────────────────────────────────────────────────────────────
PUBLIC_DUMP="$(headers_of "${ACCESS_ARGS[@]}" -H 'Accept-Encoding: identity' "${PUBLIC_URL}${DOC_PATH}")"
assert_not_access_wall "$PUBLIC_DUMP"
PUBLIC_STATUS="$(status_of "$PUBLIC_DUMP")"
[ "$PUBLIC_STATUS" = "200" ] \
    || fail "the public URL ${PUBLIC_URL}${DOC_PATH} answered '${PUBLIC_STATUS:-nothing}', not 200.
    $(transport_error "$PUBLIC_DUMP")"

PUBLIC_ETAG="$(header_value "$PUBLIC_DUMP" etag)"
[ -n "$PUBLIC_ETAG" ] \
    || fail "the public URL served no ETag, so the edge is holding a document it can
    never revalidate. This is the shape of the 2026-08-25 outage."

# ── 3. Same document? ───────────────────────────────────────────────────────
#
# Cloudflare weakens strong ETags when it transforms a response, so `W/` is
# stripped from both sides before comparing. Nothing else is normalised: the
# encoding suffix is meaningful, and two sides that disagree on it are two
# different representations, which is a real finding rather than noise.
normalise_etag() { printf '%s' "$1" | sed 's/^W\///; s/^ *//; s/ *$//'; }
if [ "$(normalise_etag "$ORIGIN_ETAG")" != "$(normalise_etag "$PUBLIC_ETAG")" ]; then
    fail "the edge is serving a DIFFERENT document than the origin.
    origin ${ORIGIN_URL}${DOC_PATH}  ETag ${ORIGIN_ETAG}
    public ${PUBLIC_URL}${DOC_PATH}  ETag ${PUBLIC_ETAG}
    The deploy is not visible to users. Purge the Cloudflare cache for this
    path, then find out why the edge did not revalidate."
fi

# ── 4. Cache-Control ────────────────────────────────────────────────────────
#
# A document may be stored; it may not be reused for hours without asking. The
# threshold is 60s rather than 0 so a deliberate short max-age stays legal,
# while the 86400 that caused the outage cannot come back unnoticed.
PUBLIC_CC="$(header_value "$PUBLIC_DUMP" cache-control)"
MAX_AGE="$(printf '%s' "$PUBLIC_CC" | grep -oE '(^|[^-])max-age=[0-9]+' | grep -oE '[0-9]+$' | sort -n | tail -n1)"
if [ -n "$MAX_AGE" ] && [ "$MAX_AGE" -ge 60 ]; then
    fail "the public document is cacheable for ${MAX_AGE}s without revalidating
    (Cache-Control: ${PUBLIC_CC}). A deploy stays invisible for that long."
fi

# ── 5. Conditional revalidation, through the edge ───────────────────────────
COND_DUMP="$(headers_of "${ACCESS_ARGS[@]}" -H 'Accept-Encoding: identity' \
    -H "If-None-Match: ${PUBLIC_ETAG}" "${PUBLIC_URL}${DOC_PATH}")"
assert_not_access_wall "$COND_DUMP"
COND_STATUS="$(status_of "$COND_DUMP")"
[ "$COND_STATUS" = "304" ] \
    || fail "a conditional request through the edge answered '${COND_STATUS:-nothing}', not 304.
    Revalidation is the whole mechanism that keeps a no-cache document cheap;
    without it every page load is a full transfer."

# ── 6. Compression, through the edge ────────────────────────────────────────
GZIP_DUMP="$(headers_of "${ACCESS_ARGS[@]}" -H 'Accept-Encoding: gzip' "${PUBLIC_URL}${DOC_PATH}")"
assert_not_access_wall "$GZIP_DUMP"
GZIP_ENC="$(header_value "$GZIP_DUMP" content-encoding)"
printf '%s' "$GZIP_ENC" | grep -qi gzip \
    || fail "the edge served '${GZIP_ENC:-no}' content-encoding to a client offering gzip."

echo "cdn-check: OK — ${PUBLIC_URL}${DOC_PATH} matches the origin (ETag ${PUBLIC_ETAG}),"
echo "           revalidates (304), negotiates gzip, and is not held past ${MAX_AGE:-0}s."
