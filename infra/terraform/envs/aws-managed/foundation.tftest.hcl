mock_provider "aws" {}

variables {
  vpc_id             = "vpc-12345678"
  private_subnet_ids = ["subnet-11111111", "subnet-22222222", "subnet-33333333"]
  public_subnet_ids  = ["subnet-44444444", "subnet-55555555"]
  certificate_arn    = "arn:aws:acm:us-east-1:123456789012:certificate/00000000-0000-0000-0000-000000000000"
  api_hostname       = "test.example.com"
  grafana_admin_ids  = ["00000000-0000-0000-0000-000000000000"]
  images = {
    market-data       = "example.com/md@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    strategy-engine   = "example.com/strategy@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    api-gateway       = "example.com/api@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    reliability-probe = "example.com/probe@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    collector         = "example.com/collector@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }
}

run "deployment_contract" {
  command = plan
  assert {
    condition     = aws_msk_cluster.this.number_of_broker_nodes == 3 && aws_msk_cluster.this.encryption_info[0].encryption_in_transit[0].client_broker == "TLS"
    error_message = "Kafka must have three brokers and require TLS."
  }
  assert {
    condition     = aws_ecs_service.this["strategy-engine"].desired_count == 1 && aws_ecs_service.this["strategy-engine"].deployment_maximum_percent == 100
    error_message = "In-memory strategy state requires a single active instance."
  }
  assert {
    condition     = alltrue([for service in aws_ecs_service.this : !service.network_configuration[0].assign_public_ip && service.deployment_circuit_breaker[0].rollback])
    error_message = "Tasks must stay private with rollback enabled."
  }
  assert {
    condition     = aws_lb_listener.https.protocol == "HTTPS"
    error_message = "Public ingress must use HTTPS."
  }
}
