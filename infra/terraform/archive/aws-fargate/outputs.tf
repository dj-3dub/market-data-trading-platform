output "ecs_cluster_name" {
  value       = aws_ecs_cluster.this.name
  description = "Name of the ECS cluster"
}

output "market_data_service_name" {
  value       = aws_ecs_service.market_data.name
  description = "Name of the ECS service for market data"
}

output "api_gateway_service_name" {
  value       = aws_ecs_service.api_gateway.name
  description = "Name of the ECS service for API gateway"
}

output "tasks_security_group_id" {
  value       = aws_security_group.tasks.id
  description = "Security group used by ECS tasks"
}
