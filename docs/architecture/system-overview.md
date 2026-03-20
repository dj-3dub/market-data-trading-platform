# System Overview

This project simulates a distributed, event-driven market data trading platform designed to demonstrate reliability engineering, observability, and production-style troubleshooting.

The system is composed of multiple containerized services communicating over a shared Docker network, with Kafka acting as the central event streaming backbone.

## High-Level Components

- **Market Data Service (Python)**
  - Generates and publishes simulated market data
  - Acts as the upstream data source

- **Kafka Broker**
  - Central event streaming platform
  - Decouples producers and consumers
  - Enables asynchronous data flow

- **Strategy Engine (C# / .NET)**
  - Consumes market data from Kafka
  - Processes data to generate trading signals or decisions
  - Exposes metrics for observability

- **API Gateway (FastAPI)**
  - Provides external access to system state
  - Aggregates data from internal services
  - Acts as a read interface for consumers

- **Prometheus**
  - Scrapes metrics from services
  - Stores time-series data

- **Grafana**
  - Visualizes system metrics
  - Enables latency, throughput, and health analysis

## Design Principles

- **Loose Coupling**
  Services communicate through Kafka rather than direct dependencies where possible.

- **Observability First**
  Metrics and dashboards are first-class components of the system.

- **Failure Awareness**
  The system is intentionally structured to support failure simulation and recovery.

- **Reproducibility**
  The entire environment can be deployed locally via Docker Compose or in AWS using Terraform.

## Deployment Modes

- **Local Development**
  - Docker Compose
  - Single-node environment
  - Ideal for testing and debugging

- **Cloud Deployment**
  - AWS ECS Fargate via Terraform
  - Scalable, container-based infrastructure

## Purpose

This system is not intended to execute real trades, but to model the operational challenges of trading systems, including:

- data flow reliability
- service dependency awareness
- observability and monitoring
- incident detection and recovery
