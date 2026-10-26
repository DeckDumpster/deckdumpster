terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.69.1"
    }
    # Same provider and pin dumpstar's infra/edge uses for its Pocket ID client.
    pocketid = {
      source  = "Trozz/pocketid"
      version = "2.4.2"
    }
  }

  # One state per instance: workspace <instance> keys at env:/<instance>/deckdumpster/pocketid/...
  backend "s3" {
    key          = "deckdumpster/pocketid/terraform.tfstate"
    region       = "us-west-2"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.aws_region

  assume_role {
    role_arn = var.deploy_role_arn
  }
}

# POCKETID_API_TOKEN (a Pocket ID admin API key) comes from the environment, never a file in git.
provider "pocketid" {
  base_url = var.pocketid_url
}
