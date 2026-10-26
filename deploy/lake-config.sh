#!/usr/bin/env bash
#
# Writes this host's lake config from the Terraform outputs in deploy/infra/lake.
#
#   bash deploy/lake-config.sh <instance> [--secrets]
#
# Writes (0600, never over a value already set):
#   ~/.config/mtgc/<instance>/lake.env   MTGC_LAKE_S3_BUCKET, MTGC_LAKE_TENANT_URI
#   ~/.aws/config                        profiles mtgc-lake and mtgc-tenant (region)
#
# --secrets also writes the two profiles' keys into ~/.aws/credentials, read from Secrets
# Manager (your own identity) straight into the file, never a terminal. A profile already
# present is left alone. The job containers mount ~/.aws read-only (mtgc-ship, mtgc-value).
#
# MTGC_LAKE_TF_OUTPUT names a file of `terraform output -json` (test seam); otherwise it is
# run in deploy/infra/lake.
set -euo pipefail

INSTANCE="${1:?usage: lake-config.sh <instance> [--secrets]}"
WITH_SECRETS=0
[ "${2:-}" = "--secrets" ] && WITH_SECRETS=1

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONF_DIR="${MTGC_CONFIG_DIR:-${HOME}/.config/mtgc}"
LAKE_ENV="${CONF_DIR}/${INSTANCE}/lake.env"
AWS_DIR="${MTGC_AWS_DIR:-${HOME}/.aws}"

if [ -n "${MTGC_LAKE_TF_OUTPUT:-}" ]; then
    OUT="$(cat "$MTGC_LAKE_TF_OUTPUT")"
else
    OUT="$(terraform -chdir="${SCRIPT_DIR}/infra/lake" output -json)"
fi
out() { printf '%s' "$OUT" | jq -er ".$1.value"; }
REGION="$(out region)"
BUCKET="$(out lake_bucket)"

# set_default <file> <key> <value>: assign the key unless the file already gives it a real
# value. A scaffolded `#KEY=...` counts as unset; anything else is kept.
set_default() {
    local file="$1" key="$2" value="$3" current
    current="$(grep -E "^${key}=" "$file" | tail -n1 | cut -d= -f2- || true)"
    if [ -n "$current" ]; then
        echo "    ${file}: ${key} already set, left alone"
        return
    fi
    if grep -qE "^#?${key}=" "$file"; then
        sed -i "s|^#\?${key}=.*|${key}=${value}|" "$file"
    else
        printf '%s=%s\n' "$key" "$value" >>"$file"
    fi
    echo "    ${file}: ${key} set"
}

mkdir -p "$(dirname "$LAKE_ENV")" "$AWS_DIR"
chmod 700 "$(dirname "$LAKE_ENV")" "$AWS_DIR"
[ -f "$LAKE_ENV" ] || : >"$LAKE_ENV"
chmod 600 "$LAKE_ENV"
set_default "$LAKE_ENV" MTGC_LAKE_S3_BUCKET "$BUCKET"
set_default "$LAKE_ENV" MTGC_LAKE_TENANT_URI "s3://${BUCKET}/tenant"

touch "$AWS_DIR/config" "$AWS_DIR/credentials"
chmod 600 "$AWS_DIR/config" "$AWS_DIR/credentials"
for p in mtgc-lake mtgc-tenant; do
    if grep -q "^\[profile ${p}\]" "$AWS_DIR/config"; then
        echo "    ${AWS_DIR}/config: profile ${p} already present, left alone"
    else
        printf '\n[profile %s]\nregion = %s\n' "$p" "$REGION" >>"$AWS_DIR/config"
        echo "    ${AWS_DIR}/config: profile ${p} added"
    fi
done

if [ "$WITH_SECRETS" = 1 ]; then
    for pair in mtgc-lake:lake_secret_name mtgc-tenant:tenant_secret_name; do
        p="${pair%%:*}"
        if grep -q "^\[${p}\]" "$AWS_DIR/credentials"; then
            echo "    ${AWS_DIR}/credentials: ${p} already present, left alone"
            continue
        fi
        {
            echo
            aws secretsmanager get-secret-value --region "$REGION" --secret-id "$(out "${pair#*:}")" \
                --query SecretString --output text |
                jq -r --arg p "$p" '"[\($p)]\naws_access_key_id=\(.AWS_ACCESS_KEY_ID)\naws_secret_access_key=\(.AWS_SECRET_ACCESS_KEY)"'
        } >>"$AWS_DIR/credentials"
        echo "    ${AWS_DIR}/credentials: ${p} written"
    done
fi
