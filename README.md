# Market Data Trading Platform

[![CI](https://github.com/dj-3dub/market-data-trading-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/dj-3dub/market-data-trading-platform/actions/workflows/ci.yml)

A **trading systems reliability lab** designed to simulate market data distribution, service dependencies, latency-sensitive processing, and production incident response in an execution-style environment.

The goal is to model how systems behave under real-time conditions — including latency sensitivity, partial failure, and recovery — rather than simply how they are deployed.

---

## Trading System Characteristics

- Latency directly impacts execution quality  
- Stale data introduces financial risk  
- Silent failures are more dangerous than outages  
- Recovery speed matters more than uptime  

This project models these constraints through a simulated data pipeline and observable system behavior.

---

## 🧠 Engineering Focus

This repository demonstrates:

- Event-driven market data pipelines  
- Service dependency awareness under failure  
- Observability of real-time data flow  
- Detection of stale or degraded system states  
- Incident triage and recovery workflows  
- Infrastructure automation and reproducibility  

---

## 🏗️ Architecture

![Architecture](docs/architecture/trading-architecture.png)

Core pipeline:

Market Data → Kafka → Strategy Engine → API → Consumers  

Monitoring layer:

All Services → Prometheus → Grafana  

---

## 🔁 Data Flow

1. Market data service publishes simulated price data  
2. Kafka distributes events asynchronously  
3. Strategy engine consumes and processes data  
4. API exposes system state  
5. Prometheus collects metrics  
6. Grafana visualizes system health  

---

## ⚙️ Core Components

### Market Data Service (Python)
Simulates upstream market data feed and publishes to Kafka.

### Kafka Broker
Event streaming backbone enabling decoupled communication.

### Strategy Engine (C# / .NET)
Consumes and processes data, producing signals and metrics.

### API Gateway (FastAPI)
Provides system visibility and exposes processed data.

### Observability Stack
Prometheus (metrics) and Grafana (dashboards).

---

## 🚨 Failure Scenarios

- Kafka broker outage  
- Consumer lag / backlog  
- Strategy engine degradation  
- API latency spikes  
- Stale data conditions  
- Partial system failure  

---

## 🔍 Observability Strategy

Key signals tracked:

- End-to-end latency  
- Message throughput  
- Consumer lag  
- Data freshness  
- Error rate  
- Restart frequency  

---

## 🛠️ Operational Playbooks

- Incident simulations (`docs/incidents/`)  
- Recovery runbooks (`docs/operations/`)  
- Troubleshooting workflows  
- Failure injection planning  
- Validation checklists  

---

## 📊 Observability

Observability is treated as a first-class component of the system.

Dashboards and datasources are provisioned via code to ensure:
- reproducibility across environments  
- zero manual configuration  
- consistent visibility into system behavior  

Key metrics visualized:
- End-to-end latency (p50 / p95 / p99)  
- Kafka consumer lag  
- Message throughput  
- Strategy processing time  
- API latency  
- Data freshness  
- Error rates  
- Service restart frequency  

Dashboards are defined in:
`monitoring/grafana/dashboards/`

---

## 📂 Project Structure

```text
.
├── .github/        # CI/CD workflows
├── docs/           # Architecture, operations, incidents, testing, resume
├── infra/          # Terraform (AWS ECS/Fargate)
├── monitoring/     # Prometheus + Grafana configuration
├── scripts/        # Helper and diagnostic scripts
├── services/       # Core application services (market data, strategy, API, frontend)
├── tools/          # Kafka utilities and supporting tools
├── .gitignore
├── docker-compose.yml
├── Makefile
└── README.md
```

The `services/` directory contains the application components used to simulate a trading-style execution environment.

---

## ▶️ Running Locally

```bash
docker compose up --build
```

Access:

- API → http://localhost:8000  
- Web UI → http://localhost:8080  
- Prometheus → http://localhost:9091  
- Grafana → http://localhost:3000  

---

## ☁️ Infrastructure

Terraform configurations are included for AWS ECS Fargate deployment.

```bash
cd infra
terraform init
terraform apply
```

---

## 🧪 Reliability Engineering Focus

This project is designed to explore:

- System behavior under failure  
- Dependency-aware debugging  
- Latency and data flow analysis  
- Recovery workflows  

---

## 🧭 Roadmap

- Latency instrumentation across services  
- Kafka consumer lag dashboards  
- Synthetic health checks  
- Failure injection scripts  
- Network degradation simulation  
- Distributed tracing (OpenTelemetry)  

---

## 🧠 Design Philosophy

This project emphasizes understanding system behavior under real-world conditions, including latency sensitivity, partial failures, and recovery workflows.

The goal is not just to deploy services, but to observe, debug, and improve them under stress.

---

## 📌 Author

Tim Heverin  
Infrastructure / Platform Engineering  
Chicago, IL  

