# deploy/lake-config.sh reads these with `terraform output -json`.
output "region" {
  value = var.aws_region
}

output "lake_bucket" {
  value = aws_s3_bucket.lake.bucket
}

output "lake_secret_name" {
  value = aws_secretsmanager_secret.lake.name
}

output "tenant_secret_name" {
  value = aws_secretsmanager_secret.tenant.name
}
