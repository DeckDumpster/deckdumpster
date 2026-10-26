# Lakehouse: bucket and roles SOP (Ryan's console steps)

One page, run once, in order. Roles, never users: every runtime identity is an
assumed role, and **every step starts by proving who you are**:

```bash
aws sts get-caller-identity --profile <profile>   # Arn must be the one the step names
```

If the Arn is not the one stated, stop. Nothing below is run by an agent.

Placeholders:

| Name | Meaning |
|---|---|
| `ACCOUNT_ID` | the AWS account |
| `LAKE` | `mtgc-lake-<suffix>`, the lake bucket |
| `BACKUP` | `gantt-mtgc-backup`, the existing nightly-backup bucket |
| `LSTREAM` | `mtgc-db-<suffix>`, the Litestream bucket |

## 1-4. Bucket, identities, lifecycle, profiles: Terraform

The console steps this page used to carry (bucket, the `mtgc-lake` and `mtgc-tenant`
identities with their mirror Denies, the tenant-zone lifecycle, the profiles) are
`deploy/infra/lake/` (law-infrastructure-is-terraform). Read the `.tf` files for the policies:

- `mtgc-lake-<account>`: private, versioned, SSE-S3, TLS-only. The one expiring prefix is
  `tenant/` (90 days, noncurrent 1 day); `raw/` and `lake/` have no rule.
- user `mtgc-lake`: get/put under `raw/` and `lake/`, no delete (append-only), denied `tenant/`;
  secret `mtgc/lake`.
- user `mtgc-tenant`: get/put/delete under `tenant/` only, denied `raw/` and `lake/`;
  secret `mtgc/tenant`.

The lifecycle Terraform applies, for reference (no rule may match `raw/` or `lake/`):

```json
{"Rules":[{"ID":"tenant-90d","Status":"Enabled",
  "Filter":{"Prefix":"tenant/"},
  "Expiration":{"Days":90},
  "NoncurrentVersionExpiration":{"NoncurrentDays":1},
  "AbortIncompleteMultipartUpload":{"DaysAfterInitiation":1}}]}
```

```bash
cd deploy/infra/lake
terraform init -backend-config=backend.tfvars   # from backend.tfvars.example
terraform test                                  # hermetic, mocked provider
terraform apply -var deploy_role_arn=<DeployRoleArn>   # MFA session, by the Concierge
bash ../../lake-config.sh <instance> --secrets  # lake.env + the mtgc-lake / mtgc-tenant profiles
```

The `mtgc` name prefix must be in the terraform-deploy role's `TERRAFORM_NAME_PREFIXES`
(ephemeral-ci) before the apply can create these names. `lake-config.sh` never overwrites a
value or profile already set. Then arm the chain: redeploy with `MTGC_ARM_LAKE_CHAIN=1`
or run `bash deploy/chain.sh arm <instance>` (it needs the tenant master key, `deploy/LAKE-KEYS.md`).
A failing lake-sync now writes its reason to the journal under `mtgc-lake-sync-<instance>`.

## 5. Verify (every line is a pass/fail, run in order)

```bash
for p in mtgc-lake mtgc-tenant; do aws sts get-caller-identity --profile $p; done  # Arn = role/$p

# allowed
echo x | aws s3 cp - s3://LAKE/raw/_probe --profile mtgc-lake
echo x | aws s3 cp - s3://LAKE/tenant/_probe --profile mtgc-tenant
# must be AccessDenied (each of these)
aws s3 ls s3://LAKE/tenant/ --profile mtgc-lake
aws s3 ls s3://LAKE/raw/    --profile mtgc-tenant
aws s3 ls s3://BACKUP/      --profile mtgc-lake
aws s3 ls s3://BACKUP/      --profile mtgc-tenant
aws s3 ls s3://LSTREAM/     --profile mtgc-lake
aws s3 rm s3://LAKE/raw/_probe --profile mtgc-lake      # raw is append-only
aws s3api put-bucket-lifecycle-configuration --bucket LAKE --lifecycle-configuration '{"Rules":[]}' --profile mtgc-tenant

# clean up the probes
aws s3 rm s3://LAKE/tenant/_probe --profile mtgc-tenant
```

Any "allowed" line failing, or any "must be AccessDenied" line succeeding, means
the policy is wrong: fix it before any job is armed. Record the account id,
bucket names and role ARNs in `~/.config/mtgc/<instance>.env` for the jobs.

## 6. Governing the tenant zone (any operator, after the console steps)

```bash
bash deploy/setup-tenant-zone.sh --render --out DIR            # the two role documents, bucket substituted
bash deploy/setup-tenant-zone.sh --apply --profile mtgc-lifecycle-admin
bash deploy/setup-tenant-zone.sh --check --profile mtgc-lifecycle-admin
```

The bucket is `MTGC_LAKE_S3_BUCKET` in `~/.config/mtgc/<instance>/lake.env`; the script
refuses a bucket equal to `MTGC_BACKUP_S3_BUCKET` / `MTGC_LITESTREAM_S3_BUCKET`.
The documents under `deploy/policies/tenant-zone/` are the ones in §2 plus
explicit Denies on the other zone's listing and on rewriting the governance.
`--check` exits **0** correct, **1** present but wrong (wrong window, or a rule
reaching `raw/`/`lake/`, or any refusal), **3** absent, **4** cannot verify (the
read was denied or failed: never reported as absent), **2** usage.
`tests/lake/tenant_zone.sh` proves every one of these, green and red, against
MinIO. Key custody: `deploy/LAKE-KEYS.md`.
