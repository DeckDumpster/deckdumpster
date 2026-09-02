#!/usr/bin/env bash
# cf-access-probe.sh — why is Cloudflare Access refusing this service token?
#
# cdn-check.sh answers "did the deploy reach users". This answers the narrower
# question underneath it: is the token itself the problem, the policy, or the
# application. It never prints a secret — only lengths, shapes and HTTP results.
#
# Usage:
#   CF_ACCESS_CLIENT_ID=... CF_ACCESS_CLIENT_SECRET=... deploy/cf-access-probe.sh [url]
set -uo pipefail
URL="${1:-https://magic.dumpster.cards}"
ID="${CF_ACCESS_CLIENT_ID:-}"
SEC="${CF_ACCESS_CLIENT_SECRET:-}"

hr() { printf '%s\n' "────────────────────────────────────────────────────────"; }

echo "target: $URL"; hr

# 1. SHAPE OF THE CREDENTIALS. Two failure modes look identical from outside and
#    are both invisible in the CI log, because Actions masks the values:
#      - a Client ID pasted without its `.access` suffix
#      - a trailing newline, which GitHub preserves verbatim in a secret
echo "credential shape (no values printed):"
if [ -z "$ID" ] || [ -z "$SEC" ]; then
  echo "  MISSING — set CF_ACCESS_CLIENT_ID and CF_ACCESS_CLIENT_SECRET"; exit 2
fi
printf '  client id:     %d chars, ends in .access: %s\n' "${#ID}" \
  "$(case "$ID" in *.access) echo yes;; *) echo NO — this is the usual paste error;; esac)"
printf '  client secret: %d chars\n' "${#SEC}"
# THE ONE THAT ACTUALLY HAPPENED (2026-08-30). Cloudflare's UI presents a service
# token as a ready-to-paste HEADER LINE:
#
#     CF-Access-Client-Id: abc123....access
#
# Paste the whole line into the secret and curl builds
# `CF-Access-Client-Id: CF-Access-Client-Id: abc123....access` — a malformed header,
# silently ignored, so Access answers every request as if unauthenticated. The CI log
# shows both variables present and masked, so it looks exactly like a policy problem.
# It cost several days and three wrong diagnoses.
for n in ID SEC; do
  v="${!n}"
  case "$v" in
    CF-Access-Client-Id:*|CF-Access-Client-Secret:*|*:\ *)
      echo "  ✗ $n INCLUDES THE HEADER NAME — the value is everything AFTER the colon."
      echo "    Cloudflare shows it as a full header line; paste only the value." ;;
  esac
  case "$v" in
    *[[:space:]]*) echo "  ⚠ $n CONTAINS WHITESPACE — a trailing newline, or the header-name paste above" ;;
  esac
done
hr

# 2. WHAT THE EDGE SAYS WITHOUT A TOKEN — establishes which Access application
#    guards this hostname. The `kid` in the redirect IS the app's aud tag.
echo "unauthenticated request:"
anon=$(curl -sS -o /dev/null -D - --max-time 20 "$URL/" 2>/dev/null)
code=$(printf '%s' "$anon" | awk 'NR==1{print $2}')
echo "  HTTP $code"
team=$(printf '%s' "$anon" | grep -oiE '[a-z0-9-]+\.cloudflareaccess\.com' | head -1)
aud=$(printf '%s' "$anon" | grep -oE 'kid=[0-9a-f]{64}' | head -1 | cut -d= -f2)
echo "  team domain: ${team:-none — Access may not be in front of this hostname}"
echo "  application: ${aud:-unknown}"
hr

# 3. THE SAME REQUEST WITH THE TOKEN. If this still redirects to the login page,
#    the token is being REFUSED rather than missing, and the question becomes
#    which application the Service Auth policy is attached to.
echo "authenticated request:"
auth=$(curl -sS -o /dev/null -D - --max-time 20 \
        -H "CF-Access-Client-Id: $ID" -H "CF-Access-Client-Secret: $SEC" "$URL/" 2>/dev/null)
acode=$(printf '%s' "$auth" | awk 'NR==1{print $2}')
echo "  HTTP $acode"
if printf '%s' "$auth" | grep -qi 'cloudflareaccess\.com'; then
  aud2=$(printf '%s' "$auth" | grep -oE 'kid=[0-9a-f]{64}' | head -1 | cut -d= -f2)
  echo "  ✗ REFUSED — still the Access login page."
  echo "    The credentials are reaching Cloudflare and being rejected."
  echo "    Check that a policy on application ${aud2:-$aud} has Action = 'Service Auth'"
  echo "    and includes THIS token. A Service Auth policy on a DIFFERENT application,"
  echo "    or one including a different token, produces exactly this."
else
  echo "  ✓ ACCEPTED — the app answered, not the login page."
  printf '%s' "$auth" | grep -iE '^(etag|cache-control|cf-cache-status|content-type):' | sed 's/^/    /'
fi
