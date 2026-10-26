# The lake bucket (deploy/LAKE-SOP.md): raw/ and lake/ are the catalog zone, kept indefinitely;
# tenant/ is the tenant zone, 90 days. Replaces the SOP's console steps 1-3, following
# dumpstar's infra/lake.tf. The CI account holds it (law-product-aws-resources-live-in-the-ci-account).
data "aws_caller_identity" "current" {}

locals {
  lake_bucket = "mtgc-lake-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket" "lake" {
  bucket = local.lake_bucket

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "lake" {
  bucket                  = aws_s3_bucket.lake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "lake" {
  bucket = aws_s3_bucket.lake.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "lake" {
  bucket = aws_s3_bucket.lake.id

  versioning_configuration {
    status = "Enabled"
  }
}

# There is deliberately no expiry on raw/ or lake/. The only expiring prefix is tenant/.
resource "aws_s3_bucket_lifecycle_configuration" "lake" {
  bucket = aws_s3_bucket.lake.id

  rule {
    id     = "tenant-zone-retention"
    status = "Enabled"

    filter {
      prefix = "tenant/"
    }

    expiration {
      days = var.tenant_zone_days
    }

    noncurrent_version_expiration {
      noncurrent_days = 1
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }

  depends_on = [aws_s3_bucket_versioning.lake]
}

data "aws_iam_policy_document" "lake_tls_only" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.lake.arn, "${aws_s3_bucket.lake.arn}/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "lake" {
  bucket     = aws_s3_bucket.lake.id
  policy     = data.aws_iam_policy_document.lake_tls_only.json
  depends_on = [aws_s3_bucket_public_access_block.lake]
}

# mtgc-lake: land, derive and prices. No DeleteObject: the raw zone is append-only.
resource "aws_iam_user" "lake" {
  name                 = "mtgc-lake"
  permissions_boundary = var.permissions_boundary_arn
  tags                 = { terraform-deploy-boundary = "true" }
}

data "aws_iam_policy_document" "lake" {
  statement {
    sid       = "CatalogZoneObjects"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:AbortMultipartUpload"]
    resources = ["${aws_s3_bucket.lake.arn}/raw/*", "${aws_s3_bucket.lake.arn}/lake/*"]
  }

  statement {
    sid       = "CatalogZoneListingIsPrefixScoped"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.lake.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["raw/*", "lake/*"]
    }
  }

  statement {
    sid       = "DenyTenantZone"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = ["${aws_s3_bucket.lake.arn}/tenant/*"]
  }
}

resource "aws_iam_user_policy" "lake" {
  name   = "mtgc-lake-rw"
  user   = aws_iam_user.lake.name
  policy = data.aws_iam_policy_document.lake.json
}

resource "aws_iam_access_key" "lake" {
  user = aws_iam_user.lake.name
}

resource "aws_secretsmanager_secret" "lake" {
  name        = "mtgc/lake"
  description = "S3 credential for the mtgc lake bucket, raw/ and lake/ (deploy/lake-config.sh reads it)"
}

resource "aws_secretsmanager_secret_version" "lake" {
  secret_id = aws_secretsmanager_secret.lake.id

  secret_string = jsonencode({
    AWS_ACCESS_KEY_ID     = aws_iam_access_key.lake.id
    AWS_SECRET_ACCESS_KEY = aws_iam_access_key.lake.secret
  })
}

# mtgc-tenant: ship and value. The only identity that may delete, and only under tenant/.
resource "aws_iam_user" "tenant" {
  name                 = "mtgc-tenant"
  permissions_boundary = var.permissions_boundary_arn
  tags                 = { terraform-deploy-boundary = "true" }
}

data "aws_iam_policy_document" "tenant" {
  statement {
    sid       = "TenantZoneObjects"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:DeleteObjectVersion", "s3:AbortMultipartUpload"]
    resources = ["${aws_s3_bucket.lake.arn}/tenant/*"]
  }

  statement {
    sid       = "TenantZoneListingIsPrefixScoped"
    actions   = ["s3:ListBucket", "s3:ListBucketVersions"]
    resources = [aws_s3_bucket.lake.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["tenant/*"]
    }
  }

  statement {
    sid       = "DenyCatalogZone"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = ["${aws_s3_bucket.lake.arn}/raw/*", "${aws_s3_bucket.lake.arn}/lake/*"]
  }
}

resource "aws_iam_user_policy" "tenant" {
  name   = "mtgc-tenant-rw"
  user   = aws_iam_user.tenant.name
  policy = data.aws_iam_policy_document.tenant.json
}

resource "aws_iam_access_key" "tenant" {
  user = aws_iam_user.tenant.name
}

resource "aws_secretsmanager_secret" "tenant" {
  name        = "mtgc/tenant"
  description = "S3 credential for the mtgc tenant zone, tenant/ of the lake bucket (deploy/lake-config.sh reads it)"
}

resource "aws_secretsmanager_secret_version" "tenant" {
  secret_id = aws_secretsmanager_secret.tenant.id

  secret_string = jsonencode({
    AWS_ACCESS_KEY_ID     = aws_iam_access_key.tenant.id
    AWS_SECRET_ACCESS_KEY = aws_iam_access_key.tenant.secret
  })
}
