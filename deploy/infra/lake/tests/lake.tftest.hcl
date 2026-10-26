# Plan-only assertions with a mocked provider: no credentials, no network.
mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    }
  }
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "123456789012"
    }
  }
}

variables {
  deploy_role_arn = "arn:aws:iam::123456789012:role/terraform-deploy"
}

override_resource {
  target          = aws_s3_bucket.lake
  override_during = plan
  values = {
    arn = "arn:aws:s3:::mtgc-lake-123456789012"
  }
}

run "bucket_is_private_versioned_and_encrypted" {
  command = plan

  assert {
    condition     = startswith(aws_s3_bucket.lake.bucket, "mtgc-lake-")
    error_message = "the bucket must carry the mtgc-lake- prefix"
  }
  assert {
    condition = alltrue([
      aws_s3_bucket_public_access_block.lake.block_public_acls,
      aws_s3_bucket_public_access_block.lake.block_public_policy,
      aws_s3_bucket_public_access_block.lake.ignore_public_acls,
      aws_s3_bucket_public_access_block.lake.restrict_public_buckets,
    ])
    error_message = "all public access must be blocked"
  }
  assert {
    condition     = aws_s3_bucket_versioning.lake.versioning_configuration[0].status == "Enabled"
    error_message = "the bucket must be versioned"
  }
  assert {
    condition     = one(aws_s3_bucket_server_side_encryption_configuration.lake.rule).apply_server_side_encryption_by_default[0].sse_algorithm == "AES256"
    error_message = "the bucket must be encrypted by default"
  }
}

run "lifecycle_touches_only_tenant" {
  command = plan

  assert {
    condition     = length(aws_s3_bucket_lifecycle_configuration.lake.rule) == 1
    error_message = "the lake has exactly one lifecycle rule"
  }
  assert {
    condition = alltrue([
      for r in aws_s3_bucket_lifecycle_configuration.lake.rule :
      r.filter[0].prefix == "tenant/" && r.expiration[0].days == 90
    ])
    error_message = "the only expiry is tenant/ at 90 days; raw/ and lake/ never expire"
  }
}

run "identities_are_mirror_images_and_bounded" {
  command = plan

  assert {
    condition = alltrue(flatten([
      for d in [data.aws_iam_policy_document.lake, data.aws_iam_policy_document.tenant] :
      [for s in d.statement : [for r in s.resources : startswith(r, "arn:aws:s3:::mtgc-lake-")]]
    ]))
    error_message = "both policies name the lake bucket only"
  }
  assert {
    condition = alltrue([
      for s in data.aws_iam_policy_document.lake.statement :
      !contains(s.actions, "s3:DeleteObject") && !contains(s.actions, "s3:DeleteObjectVersion")
    ])
    error_message = "mtgc-lake may not delete: the raw zone is append-only"
  }
  assert {
    condition = anytrue([
      for s in data.aws_iam_policy_document.lake.statement :
      s.effect == "Deny" && contains(s.resources, "arn:aws:s3:::mtgc-lake-123456789012/tenant/*")
    ])
    error_message = "mtgc-lake must be explicitly denied tenant/"
  }
  assert {
    condition = anytrue([
      for s in data.aws_iam_policy_document.tenant.statement :
      s.effect == "Deny" && contains(s.resources, "arn:aws:s3:::mtgc-lake-123456789012/raw/*") && contains(s.resources, "arn:aws:s3:::mtgc-lake-123456789012/lake/*")
    ])
    error_message = "mtgc-tenant must be explicitly denied raw/ and lake/"
  }
  assert {
    condition = alltrue([
      for u in [aws_iam_user.lake, aws_iam_user.tenant] :
      u.tags["terraform-deploy-boundary"] == "true" && u.permissions_boundary == var.permissions_boundary_arn
    ])
    error_message = "both users must carry the deploy boundary and tag"
  }
}
