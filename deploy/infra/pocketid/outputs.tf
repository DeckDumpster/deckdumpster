output "cdn_check_secret_name" {
  value       = aws_secretsmanager_secret.cdn_check.name
  description = "Secrets Manager name holding the magic-cdn-check client id and secret."
}
