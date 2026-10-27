# Pocket ID OIDC client for native sign-in (mtg_collector/oidc.py), following dumpstar's
# infra/edge pocketid_client + edge secret pattern.

resource "pocketid_client" "this" {
  name                 = "magic-${var.instance}"
  callback_urls        = ["https://${var.hostname}/auth/callback"]
  logout_callback_urls = ["https://${var.hostname}/"]
  allowed_user_groups  = var.pocketid_group_ids
  pkce_enabled         = true
}

# The client secret goes to Secrets Manager and is never an output, so no plan or apply log
# carries it. deploy/oidc-env.sh reads it into the instance's oidc.env on the host.
resource "aws_secretsmanager_secret" "oidc" {
  name = "${var.secret_prefix}/${var.instance}/oidc"
}

resource "aws_secretsmanager_secret_version" "oidc" {
  secret_id = aws_secretsmanager_secret.oidc.id
  secret_string = jsonencode({
    MTGC_OIDC_CLIENT_ID     = pocketid_client.this.id
    MTGC_OIDC_CLIENT_SECRET = pocketid_client.this.client_secret
  })

  lifecycle {
    precondition {
      condition = alltrue([for v in [
        pocketid_client.this.id,
        pocketid_client.this.client_secret,
      ] : v != null && v != ""])
      error_message = "the OIDC secret for ${var.instance} would carry an empty client id or secret"
    }
  }
}

# Machine caller for deploy/cdn-check.sh: client_credentials only, so no redirect URIs and no
# user groups. The app admits it on /health when its client id is in MTGC_MACHINE_CLIENTS.
resource "pocketid_client" "cdn_check" {
  name          = "magic-cdn-check-${var.instance}"
  callback_urls = []
  is_public     = false
  pkce_enabled  = false
}

resource "aws_secretsmanager_secret" "cdn_check" {
  name = "${var.secret_prefix}/${var.instance}/cdn-check"
}

resource "aws_secretsmanager_secret_version" "cdn_check" {
  secret_id = aws_secretsmanager_secret.cdn_check.id
  secret_string = jsonencode({
    MTGC_CDN_CHECK_CLIENT_ID     = pocketid_client.cdn_check.id
    MTGC_CDN_CHECK_CLIENT_SECRET = pocketid_client.cdn_check.client_secret
  })

  lifecycle {
    precondition {
      condition = alltrue([for v in [
        pocketid_client.cdn_check.id,
        pocketid_client.cdn_check.client_secret,
      ] : v != null && v != ""])
      error_message = "the cdn-check secret for ${var.instance} would carry an empty client id or secret"
    }
  }
}
