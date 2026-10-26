variable "aws_region" {
  type    = string
  default = "us-west-2"
}

variable "deploy_role_arn" {
  type        = string
  description = "DeployRoleArn output of TerraformBootstrap (role terraform-deploy)."
}

variable "permissions_boundary_arn" {
  type        = string
  description = "Boundary the terraform-deploy role requires on every IAM user it creates."
  default     = "arn:aws:iam::189923011121:policy/terraform-deploy-boundary"
}

variable "tenant_zone_days" {
  type        = number
  description = "Days an object under tenant/ is kept (deploy/LAKE-SOP.md: 90)."
  default     = 90
}
