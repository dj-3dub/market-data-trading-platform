variable "aws_region" {
  type    = string
  default = "us-east-1"
}
variable "name" {
  type    = string
  default = "trading-reliability"
}
variable "vpc_id" {
  type = string
}
variable "private_subnet_ids" {
  description = "Three private subnets in distinct AZs, with NAT or required VPC endpoints."
  type        = list(string)
  validation {
    condition     = length(var.private_subnet_ids) == 3
    error_message = "Supply three private subnets in distinct AZs for MSK."
  }
}
variable "public_subnet_ids" {
  type = list(string)
}
variable "certificate_arn" {
  description = "ACM certificate for the public API domain in this region."
  type        = string
}
variable "api_hostname" {
  description = "DNS name pointing to the ALB; used by the independent probe."
  type        = string
}
variable "images" {
  description = "Immutable image URIs for market-data, strategy-engine, api-gateway, reliability-probe and collector."
  type        = map(string)
  validation {
    condition = alltrue([for key in ["market-data", "strategy-engine", "api-gateway", "reliability-probe", "collector"] :
    can(regex("@sha256:[a-f0-9]{64}$", var.images[key]))])
    error_message = "All five images must be provided using immutable sha256 digests."
  }
}
variable "grafana_admin_ids" {
  description = "IAM Identity Center user IDs granted Grafana administrator access."
  type        = list(string)
}
