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
#   7. An asset the document names is content-addressed, and the edge serves it
#      immutable and identical to the origin (de-l23).
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

# ── 7. The assets the document names ────────────────────────────────────────
#
# Since de-l23 the server rewrites each /static reference to carry the digest of
# its bytes, and answers that URL `immutable` for a year. Two things can go
# wrong at the edge and neither is visible from localhost: the rewrite may not
# reach the public document at all, and the edge may serve an asset that is not
# what the origin holds -- which, under a year-long promise, is a cache nobody
# can revalidate out of. Both are checked here for the same reason step 3
# exists.
#
# This step cannot pass by skipping either: a document that names no
# content-addressed asset is itself the finding.
BODY="$(curl -sS -k -m 20 "${ACCESS_ARGS[@]}" -H 'Accept-Encoding: identity' \
    "${PUBLIC_URL}${DOC_PATH}" 2>/dev/null)"
ASSET_PATH="$(printf '%s' "$BODY" \
    | grep -oE '/static/[A-Za-z0-9_./-]+\.[0-9a-f]{16}\.[A-Za-z0-9]+' | head -n1)"
[ -n "$ASSET_PATH" ] \
    || fail "the public document names no content-addressed asset. Every /static
    reference should carry a digest (/static/shared.<16 hex>.css); without one
    each asset costs a conditional round trip per page load, and an origin that
    stopped rewriting them is the reason."

ASSET_ORIGIN="$(headers_of -H 'Accept-Encoding: identity' "${ORIGIN_URL}${ASSET_PATH}")"
[ "$(status_of "$ASSET_ORIGIN")" = "200" ] \
    || fail "the origin answered '$(status_of "$ASSET_ORIGIN")' for ${ASSET_PATH}, an asset
    URL its own document names. The page renders unstyled."

ASSET_DUMP="$(headers_of "${ACCESS_ARGS[@]}" -H 'Accept-Encoding: identity' \
    "${PUBLIC_URL}${ASSET_PATH}")"
assert_not_access_wall "$ASSET_DUMP"
[ "$(status_of "$ASSET_DUMP")" = "200" ] \
    || fail "the edge answered '$(status_of "$ASSET_DUMP")' for ${ASSET_PATH}.
    $(transport_error "$ASSET_DUMP")
    The document names it, so the page renders unstyled for every user."

ASSET_CC="$(header_value "$ASSET_DUMP" cache-control)"
ASSET_MAX_AGE="$(printf '%s' "$ASSET_CC" | grep -oE '(^|[^-])max-age=[0-9]+' | grep -oE '[0-9]+$' | sort -n | tail -n1)"
printf '%s' "$ASSET_CC" | grep -qi immutable && [ -n "$ASSET_MAX_AGE" ] && [ "$ASSET_MAX_AGE" -ge 86400 ] \
    || fail "a content-addressed asset is served '${ASSET_CC:-no Cache-Control}'. The digest
    in ${ASSET_PATH} is what makes a long immutable window correct; serving it
    without one pays for the URL and takes none of the benefit."

if [ "$(normalise_etag "$(header_value "$ASSET_DUMP" etag)")" \
     != "$(normalise_etag "$(header_value "$ASSET_ORIGIN" etag)")" ]; then
    fail "the edge is serving DIFFERENT bytes than the origin for ${ASSET_PATH}.
    origin ETag $(header_value "$ASSET_ORIGIN" etag)
    public ETag $(header_value "$ASSET_DUMP" etag)
    A digest-bearing URL means one exact byte string, and the edge is promising
    to hold what it has for ${ASSET_MAX_AGE}s. Purge this path."
fi

echo "cdn-check: OK — ${PUBLIC_URL}${DOC_PATH} matches the origin (ETag ${PUBLIC_ETAG}),"
echo "           revalidates (304), negotiates gzip, and is not held past ${MAX_AGE:-0}s."
echo "           ${ASSET_PATH} matches the origin and is immutable for ${ASSET_MAX_AGE}s."
