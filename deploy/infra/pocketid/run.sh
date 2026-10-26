#!/usr/bin/env bash
# bash run.sh <instance> <plan|apply> [terraform args]
# Needs backend.tfvars (bucket, assume_role = { role_arn = ... }) and common.tfvars (see
# common.tfvars.example) beside it, and POCKETID_API_TOKEN in the environment.
set -euo pipefail
inst="${1:?usage: run.sh <instance> <plan|apply>}"
verb="${2:?plan|apply}"
shift 2
cd "$(dirname "$0")"
terraform init -input=false -reconfigure -backend-config=backend.tfvars >/dev/null
terraform workspace select -or-create "$inst" >/dev/null
case "$verb" in
plan | apply) terraform "$verb" -var-file=common.tfvars -var "instance=$inst" "$@" ;;
*) echo "run.sh: unknown verb $verb" >&2; exit 1 ;;
esac
