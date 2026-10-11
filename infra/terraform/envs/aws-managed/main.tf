terraform {
  required_version = ">= 1.9.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  backend "s3" {}
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = { Project = var.name, ManagedBy = "terraform" }
  }
}

resource "aws_ecs_cluster" "this" {
  name = var.name
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}
resource "aws_cloudwatch_log_group" "this" {
  name              = "/ecs/${var.name}"
  retention_in_days = 30
}
resource "aws_service_discovery_private_dns_namespace" "this" {
  name = "${var.name}.internal"
  vpc  = var.vpc_id
}
resource "aws_security_group" "tasks" {
  name   = "${var.name}-tasks"
  vpc_id = var.vpc_id
  ingress {
    protocol  = "tcp"
    from_port = 0
    to_port   = 65535
    self      = true
  }
  ingress {
    protocol        = "tcp"
    from_port       = 8000
    to_port         = 8000
    security_groups = [aws_security_group.alb.id]
  }
  egress {
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "aws_security_group" "alb" {
  name   = "${var.name}-alb"
  vpc_id = var.vpc_id
  ingress {
    protocol    = "tcp"
    from_port   = 443
    to_port     = 443
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "aws_security_group" "kafka" {
  name   = "${var.name}-kafka"
  vpc_id = var.vpc_id
  ingress {
    protocol        = "tcp"
    from_port       = 9094
    to_port         = 9094
    security_groups = [aws_security_group.tasks.id]
  }
  ingress {
    protocol  = "-1"
    from_port = 0
    to_port   = 0
    self      = true
  }
  egress {
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "aws_msk_configuration" "this" {
  name              = var.name
  kafka_versions    = ["3.6.0"]
  server_properties = <<-EOT
    auto.create.topics.enable=true
    default.replication.factor=3
    min.insync.replicas=2
    num.partitions=1
  EOT
}
resource "aws_msk_cluster" "this" {
  cluster_name           = var.name
  kafka_version          = "3.6.0"
  number_of_broker_nodes = 3
  broker_node_group_info {
    instance_type   = "kafka.m5.large"
    client_subnets  = var.private_subnet_ids
    security_groups = [aws_security_group.kafka.id]
    storage_info {
      ebs_storage_info {
        volume_size = 100
      }
    }
  }
  encryption_info {
    encryption_in_transit {
      client_broker = "TLS"
      in_cluster    = true
    }
  }
  client_authentication {
    unauthenticated = true
  }
  configuration_info {
    arn      = aws_msk_configuration.this.arn
    revision = aws_msk_configuration.this.latest_revision
  }
}

resource "aws_iam_role" "execution" {
  name = "${var.name}-execution"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "ecs-tasks.amazonaws.com" }
  }] })
}
resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}
resource "aws_iam_role" "collector" {
  name               = "${var.name}-collector"
  assume_role_policy = aws_iam_role.execution.assume_role_policy
}
resource "aws_prometheus_workspace" "this" {
  alias = var.name
}
resource "aws_iam_role_policy" "remote_write" {
  role = aws_iam_role.collector.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = ["aps:RemoteWrite"], Resource = aws_prometheus_workspace.this.arn
  }] })
}
resource "aws_prometheus_rule_group_namespace" "slo" {
  name         = "reliability"
  workspace_id = aws_prometheus_workspace.this.id
  data         = file("${path.module}/../../../../monitoring/prometheus/slo.yml")
}
resource "aws_prometheus_rule_group_namespace" "components" {
  name         = "components"
  workspace_id = aws_prometheus_workspace.this.id
  data         = file("${path.module}/../../../../monitoring/prometheus/alerts.yml")
}

resource "aws_ecr_repository" "services" {
  for_each             = local.services
  name                 = "${var.name}/${each.key}"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
}

locals {
  namespace = aws_service_discovery_private_dns_namespace.this.name
  services = {
    market-data       = { port = 7001, count = 1 }
    strategy-engine   = { port = 7002, count = 1 }
    api-gateway       = { port = 8000, count = 2 }
    reliability-probe = { port = 8010, count = 1 }
    collector         = { port = 9090, count = 1 }
  }
  environment = [
    { name = "KAFKA_BOOTSTRAP_SERVERS", value = aws_msk_cluster.this.bootstrap_brokers_tls },
    { name = "KAFKA_SECURITY_PROTOCOL", value = "SSL" },
    { name = "MARKET_DATA_URL", value = "http://market-data.${local.namespace}:7001" },
    { name = "STRATEGY_URL", value = "http://strategy-engine.${local.namespace}:7002" },
    { name = "PROBE_URL", value = "https://${var.api_hostname}/strategy" },
    { name = "DISCOVERY_NAMESPACE", value = local.namespace },
    { name = "AMP_REMOTE_WRITE_URL", value = "${aws_prometheus_workspace.this.prometheus_endpoint}api/v1/remote_write" },
    { name = "AWS_REGION", value = var.aws_region }
  ]
}
resource "aws_service_discovery_service" "this" {
  for_each = local.services
  name     = each.key
  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.this.id
    dns_records {
      ttl  = 10
      type = "A"
    }
    routing_policy = "MULTIVALUE"
  }
  health_check_custom_config {
    failure_threshold = 1
  }
}
resource "aws_ecs_task_definition" "this" {
  for_each                 = local.services
  family                   = "${var.name}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = each.key == "collector" ? aws_iam_role.collector.arn : null
  container_definitions = jsonencode([{
    name         = each.key, image = var.images[each.key], essential = true,
    portMappings = [{ containerPort = each.value.port, protocol = "tcp" }],
    environment  = local.environment,
    healthCheck = {
      command = each.key == "strategy-engine" ? ["CMD", "curl", "-fsS", "--max-time", "3", "http://localhost:7002/health"] : [
        "CMD", "python", "-c",
        "import urllib.request; urllib.request.urlopen('http://localhost:${each.value.port}/${each.key == "collector" ? "-/healthy" : each.key == "reliability-probe" ? "metrics" : "health"}', timeout=3)"
      ],
      interval = 10, timeout = 5, retries = 3, startPeriod = 60
    },
    logConfiguration = { logDriver = "awslogs", options = {
      awslogs-group         = aws_cloudwatch_log_group.this.name, awslogs-region = var.aws_region,
      awslogs-stream-prefix = each.key
    } }
  }])
}
resource "aws_ecs_service" "this" {
  for_each                           = local.services
  name                               = each.key
  cluster                            = aws_ecs_cluster.this.id
  task_definition                    = aws_ecs_task_definition.this[each.key].arn
  desired_count                      = each.value.count
  launch_type                        = "FARGATE"
  deployment_minimum_healthy_percent = each.key == "api-gateway" ? 100 : 0
  deployment_maximum_percent         = each.key == "api-gateway" ? 200 : 100
  wait_for_steady_state              = true
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = false
  }
  service_registries {
    registry_arn = aws_service_discovery_service.this[each.key].arn
  }
  dynamic "load_balancer" {
    for_each = each.key == "api-gateway" ? [1] : []
    content {
      target_group_arn = aws_lb_target_group.api.arn
      container_name   = each.key
      container_port   = each.value.port
    }
  }
  depends_on = [aws_lb_listener.https, aws_iam_role_policy_attachment.execution, aws_iam_role_policy.remote_write]
}
resource "aws_lb" "this" {
  name               = var.name
  load_balancer_type = "application"
  subnets            = var.public_subnet_ids
  security_groups    = [aws_security_group.alb.id]
}
resource "aws_lb_target_group" "api" {
  name        = var.name
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id
  health_check {
    path = "/health"
  }
}
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  certificate_arn   = var.certificate_arn
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}
resource "aws_iam_role" "grafana" {
  name = "${var.name}-grafana"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "grafana.amazonaws.com" }
  }] })
}
resource "aws_iam_role_policy_attachment" "grafana" {
  role       = aws_iam_role.grafana.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonPrometheusReadOnlyAccess"
}
resource "aws_grafana_workspace" "this" {
  name                     = var.name
  account_access_type      = "CURRENT_ACCOUNT"
  authentication_providers = ["AWS_SSO"]
  permission_type          = "CUSTOMER_MANAGED"
  role_arn                 = aws_iam_role.grafana.arn
  data_sources             = ["PROMETHEUS"]
}
resource "aws_grafana_role_association" "admins" {
  role         = "ADMIN"
  user_ids     = var.grafana_admin_ids
  workspace_id = aws_grafana_workspace.this.id
}
