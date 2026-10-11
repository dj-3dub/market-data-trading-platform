variable "aws_region" {
  type        = string
  description = "AWS region to deploy into"
  default     = "us-east-1"
}

variable "project_name" {
  type        = string
  description = "Base name for all resources"
  default     = "market-data-trading-platform"
}

variable "vpc_id" {
  type        = string
  description = "ID of the VPC to deploy ECS services into"
}

variable "public_subnet_ids" {
  type        = list(string)
  description = "List of public subnet IDs for Fargate tasks"
}

variable "market_data_image" {
  type        = string
  description = "Container image for the market data service"
}

variable "api_gateway_image" {
  type        = string
  description = "Container image for the API gateway service"
}
