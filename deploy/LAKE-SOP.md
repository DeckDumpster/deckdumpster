# Lakehouse: bucket and roles SOP (Ryan's console steps)

One page, run once, in order. Roles, never users: every runtime identity is an
assumed role, and **every step starts by proving who you are**:

```bash
aws sts get-caller-identity --profile <profile>   # Arn must be the one the step names
```

If the Arn is not the one stated, stop. Nothing below is run by an agent.

Placeholders — pick them once and use them throughout:

| Name | Meaning |
|---|---|
| `ACCOUNT_ID` | the AWS account |
| `LAKE` | `mtgc-lake-<suffix>`, the lake bucket |
| `BACKUP` | `gantt-mtgc-backup`, the existing nightly-backup bucket |
| `LSTREAM` | `mtgc-db-<suffix>`, the Litestream bucket |

## 1. Lake bucket (as `mtgc-admin`)

One bucket, two governed zones, separated by prefix:

- `raw/` and `lake/` — the catalog zone (verbatim upstream fetches, Iceberg tables)
- `tenant/` — the tenant zone (encrypted holdings Parquet)

```bash
aws sts get-caller-identity --profile mtgc-admin
aws s3api create-bucket --bucket LAKE --region <region> --profile mtgc-admin
aws s3api put-public-access-block --bucket LAKE --profile mtgc-admin \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-versioning --bucket LAKE --profile mtgc-admin \
  --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption --bucket LAKE --profile mtgc-admin \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
```

Versioning is on for `raw/` and `lake/` (the lake is the source of rebuilds). The
tenant zone must be **deletable**, so step 4 expires noncurrent versions there too.

## 2. Roles with mirror Denies (as `mtgc-admin`)

Two roles, each trusted by the instance's base profile (`source_profile`), each
with an Allow on its own zone and **explicit Denies on everything else**. An
explicit Deny wins over any Allow added later, which is the point: a mistaken
future grant cannot make the catalog role read tenant data or the reverse.

**`role/mtgc-lake`** — land, derive, prices jobs:

```json
{ "Version": "2012-10-17", "Statement": [
  { "Effect": "Allow", "Action": ["s3:GetObject","s3:PutObject","s3:AbortMultipartUpload"],
    "Resource": ["arn:aws:s3:::LAKE/raw/*","arn:aws:s3:::LAKE/lake/*"] },
  { "Effect": "Allow", "Action": ["s3:ListBucket"], "Resource": "arn:aws:s3:::LAKE",
    "Condition": { "StringLike": { "s3:prefix": ["raw/*","lake/*"] } } },
  { "Effect": "Deny", "Action": "s3:*",
    "Resource": ["arn:aws:s3:::LAKE/tenant/*"] },
  { "Effect": "Deny", "Action": "s3:*",
    "Resource": ["arn:aws:s3:::BACKUP","arn:aws:s3:::BACKUP/*","arn:aws:s3:::LSTREAM","arn:aws:s3:::LSTREAM/*"] }
]}
```

**`role/mtgc-tenant`** — ship and value jobs (mirror image):

```json
{ "Version": "2012-10-17", "Statement": [
  { "Effect": "Allow", "Action": ["s3:GetObject","s3:PutObject","s3:DeleteObject","s3:DeleteObjectVersion","s3:AbortMultipartUpload"],
    "Resource": "arn:aws:s3:::LAKE/tenant/*" },
  { "Effect": "Allow", "Action": ["s3:ListBucket","s3:ListBucketVersions"], "Resource": "arn:aws:s3:::LAKE",
    "Condition": { "StringLike": { "s3:prefix": ["tenant/*"] } } },
  { "Effect": "Deny", "Action": "s3:*",
    "Resource": ["arn:aws:s3:::LAKE/raw/*","arn:aws:s3:::LAKE/lake/*"] },
  { "Effect": "Deny", "Action": "s3:*",
    "Resource": ["arn:aws:s3:::BACKUP","arn:aws:s3:::BACKUP/*","arn:aws:s3:::LSTREAM","arn:aws:s3:::LSTREAM/*"] }
]}
```

Notes: `mtgc-lake` has no `DeleteObject` — the raw zone is append-only. Only
`mtgc-tenant` can delete, and only under `tenant/`; that is what makes an erase
possible and provable. Neither role has any lifecycle or bucket-policy action.

## 3. Lifecycle-admin grant (as `mtgc-admin`)

Bucket lifecycle configuration is **not** granted to either runtime role. Create
`role/mtgc-lifecycle-admin` (human-assumed, no job uses it) allowing only:

```json
{ "Effect": "Allow",
  "Action": ["s3:PutLifecycleConfiguration","s3:GetLifecycleConfiguration"],
  "Resource": "arn:aws:s3:::LAKE" }
```

Then, as that role (`sts get-caller-identity` first), apply the tenant zone's
90-day lifecycle, scoped to `tenant/` only:

```bash
aws s3api put-bucket-lifecycle-configuration --bucket LAKE --profile mtgc-lifecycle-admin \
  --lifecycle-configuration '{"Rules":[{"ID":"tenant-90d","Status":"Enabled",
    "Filter":{"Prefix":"tenant/"},
    "Expiration":{"Days":90},
    "NoncurrentVersionExpiration":{"NoncurrentDays":1},
    "AbortIncompleteMultipartUpload":{"DaysAfterInitiation":1}}]}'
```

No rule may match `raw/` or `lake/`.

## 4. Profiles (on the deploy box, `~/.aws/config`)

```ini
[profile mtgc-lake]
role_arn = arn:aws:iam::ACCOUNT_ID:role/mtgc-lake
source_profile = default

[profile mtgc-tenant]
role_arn = arn:aws:iam::ACCOUNT_ID:role/mtgc-tenant
source_profile = default

[profile mtgc-lifecycle-admin]
role_arn = arn:aws:iam::ACCOUNT_ID:role/mtgc-lifecycle-admin
source_profile = default
```

The existing `mtgc-backup` profile is unchanged and keeps no access to `LAKE`.
Each job container gets exactly one profile: land/derive/prices → `mtgc-lake`,
ship/value → `mtgc-tenant`.

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
