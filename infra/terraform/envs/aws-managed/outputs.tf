output "alb_dns_name" {
  value = aws_lb.this.dns_name
}
output "cluster_name" {
  value = aws_ecs_cluster.this.name
}
output "prometheus_endpoint" {
  value = aws_prometheus_workspace.this.prometheus_endpoint
}
output "grafana_endpoint" {
  value = aws_grafana_workspace.this.endpoint
}
