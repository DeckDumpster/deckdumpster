variable "aws_region" {
  type    = string
  default = "us-west-2"
}

variable "deploy_role_arn" {
  type        = string
  description = "DeployRoleArn output of TerraformBootstrap (role terraform-deploy)."
}

variable "instance" {
  type        = string
  description = "mtgc instance name (the workspace); prod is magic.dumpster.cards."
}

variable "hostname" {
  type        = string
  description = "Public hostname the instance is served on (magic.dumpster.cards)."
}

variable "pocketid_url" {
  type    = string
  default = "https://id.gantt.pub"
}

variable "pocketid_group_ids" {
  type        = list(string)
  description = "Pocket ID group ids allowed on the client (the required group, magic-users)."
}

variable "secret_prefix" {
  type    = string
  default = "mtgc"
}
