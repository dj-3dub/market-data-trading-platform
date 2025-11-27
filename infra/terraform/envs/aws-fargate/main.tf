terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  # Dummy values so Terraform stops trying to auto-discover creds
  access_key = "DUMMY_ACCESS_KEY"
  secret_key = "DUMMY_SECRET_KEY"

  # Tell the provider NOT to talk to AWS for validation / metadata
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
}

# -------------------------
# ECS Cluster
# -------------------------
resource "aws_ecs_cluster" "this" {
  name = "${var.project_name}-cluster"
}

# -------------------------
# CloudWatch Logs
# -------------------------
resource "aws_cloudwatch_log_group" "this" {
  name              = "/ecs/${var.project_name}"
  retention_in_days = 7
}

# -------------------------
# Task Execution Role
# -------------------------
resource "aws_iam_role" "ecs_task_execution_role" {
  name = "${var.project_name}-ecs-task-exec"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = "sts:AssumeRole",
        Effect = "Allow",
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution" {
  role       = aws_iam_role.ecs_task_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# -------------------------
# Security Group for Fargate tasks
# -------------------------
resource "aws_security_group" "tasks" {
  name        = "${var.project_name}-tasks-sg"
  description = "Security group for Fargate tasks"
  vpc_id      = var.vpc_id

  ingress {
    description = "HTTP from anywhere"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# -------------------------
# Market Data Task Definition
# -------------------------
resource "aws_ecs_task_definition" "market_data" {
  family                   = "${var.project_name}-market-data"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn

  container_definitions = jsonencode([
    {
      name      = "market-data",
      image     = var.market_data_image,
      essential = true,
      portMappings = [
        {
          containerPort = 7001
          hostPort      = 7001
          protocol      = "tcp"
        }
      ],
      environment = [
        {
          name  = "SERVICE_NAME"
          value = "market-data"
        }
      ],
      logConfiguration = {
        logDriver = "awslogs",
        options = {
          awslogs-group         = aws_cloudwatch_log_group.this.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "market-data"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "market_data" {
  name            = "${var.project_name}-market-data"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.market_data.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.public_subnet_ids
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = true
  }
}

# -------------------------
# API Gateway Task Definition
# -------------------------
resource "aws_ecs_task_definition" "api_gateway" {
  family                   = "${var.project_name}-api-gateway"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn

  container_definitions = jsonencode([
    {
      name      = "api-gateway",
      image     = var.api_gateway_image,
      essential = true,
      portMappings = [
        {
          containerPort = 8000
          hostPort      = 8000
          protocol      = "tcp"
        }
      ],
      environment = [
        {
          name  = "MARKET_DATA_URL"
          value = "http://market-data:7001"
        }
      ],
      logConfiguration = {
        logDriver = "awslogs",
        options = {
          awslogs-group         = aws_cloudwatch_log_group.this.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "api-gateway"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "api_gateway" {
  name            = "${var.project_name}-api-gateway"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.api_gateway.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.public_subnet_ids
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = true
  }
}
