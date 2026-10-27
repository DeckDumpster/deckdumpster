#!/usr/bin/env bash
# Deliver native Pocket ID sign-in settings into an instance's oidc.env (never git).
#   bash deploy/oidc-env.sh <instance> <hostname>
# Reads the client id/secret terraform put in Secrets Manager (deploy/infra/pocketid), and
# generates the cookie key and the automation bearer token once -- an existing value is kept so
# a re-run does not sign everyone out or break the deploy job's token. Needs the aws CLI with
# read access to <MTGC_SECRET_PREFIX:-mtgc>/<instance>/oidc. Then: bash deploy/deploy.sh <instance>.
set -euo pipefail
instance="${1:?usage: oidc-env.sh <instance> <hostname>}"
host="${2:?usage: oidc-env.sh <instance> <hostname>}"
prefix="${MTGC_SECRET_PREFIX:-mtgc}"
dir="${HOME}/.config/mtgc/${instance}"
file="${dir}/oidc.env"

existing() { [ -f "$file" ] && grep -E "^$1=" "$file" | tail -n1 | cut -d= -f2- || true; }

secret=$(aws secretsmanager get-secret-value --secret-id "${prefix}/${instance}/oidc" \
    --query SecretString --output text)
id=$(printf '%s' "$secret" | python3 -c 'import json,sys; print(json.load(sys.stdin)["MTGC_OIDC_CLIENT_ID"])')
sec=$(printf '%s' "$secret" | python3 -c 'import json,sys; print(json.load(sys.stdin)["MTGC_OIDC_CLIENT_SECRET"])')
[ -n "$id" ] && [ -n "$sec" ] || { echo "oidc-env.sh: empty client id or secret" >&2; exit 1; }
cookie=$(existing MTGC_OIDC_COOKIE_KEY)
cookie=${cookie:-$(openssl rand -hex 32)}
token=$(existing MTGC_AUTOMATION_TOKEN)
token=${token:-$(openssl rand -hex 32)}

# Machine caller (cdn-check): its client id joins MTGC_MACHINE_CLIENTS; id and secret go to
# cdn-check.env beside oidc.env, never the repo. MTGC_HEALTH_REQUIRE_AUTH is kept if set.
cc=$(aws secretsmanager get-secret-value --secret-id "${prefix}/${instance}/cdn-check" \
    --query SecretString --output text)
ccid=$(printf '%s' "$cc" | python3 -c 'import json,sys; print(json.load(sys.stdin)["MTGC_CDN_CHECK_CLIENT_ID"])')
ccsec=$(printf '%s' "$cc" | python3 -c 'import json,sys; print(json.load(sys.stdin)["MTGC_CDN_CHECK_CLIENT_SECRET"])')
[ -n "$ccid" ] && [ -n "$ccsec" ] || { echo "oidc-env.sh: empty cdn-check client id or secret" >&2; exit 1; }
health=$(existing MTGC_HEALTH_REQUIRE_AUTH)
health=${health:-0}

mkdir -p "$dir"
chmod 700 "$dir"
umask 077
tmp=$(mktemp "${dir}/oidc.env.XXXXXX")
cat > "$tmp" <<ENV
# Written by deploy/oidc-env.sh. Bare values only (EnvironmentFile= keeps inline comments).
MTGC_OIDC_ISSUER=https://id.gantt.pub
MTGC_OIDC_CLIENT_ID=${id}
MTGC_OIDC_CLIENT_SECRET=${sec}
MTGC_OIDC_REDIRECT_URL=https://${host}/auth/callback
MTGC_OIDC_REQUIRED_GROUP=magic-users
MTGC_OIDC_COOKIE_KEY=${cookie}
MTGC_AUTOMATION_TOKEN=${token}
MTGC_MACHINE_CLIENTS=${ccid}
MTGC_HEALTH_REQUIRE_AUTH=${health}
ENV
mv "$tmp" "$file"
chmod 600 "$file"
ccfile="${dir}/cdn-check.env"
cctmp=$(mktemp "${dir}/cdn-check.env.XXXXXX")
printf 'MTGC_CDN_CHECK_CLIENT_ID=%s\nMTGC_CDN_CHECK_CLIENT_SECRET=%s\n' "$ccid" "$ccsec" > "$cctmp"
mv "$cctmp" "$ccfile"
chmod 600 "$ccfile"
echo "oidc-env.sh: wrote ${file} and ${ccfile}"
