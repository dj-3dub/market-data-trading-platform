# Market Data Trading Platform

[![CI](https://github.com/dj-3dub/market-data-trading-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/dj-3dub/market-data-trading-platform/actions/workflows/ci.yml)

A **trading systems reliability lab** designed to simulate market data distribution, service dependencies, latency-sensitive processing, and production incident response in an execution-style environment.

This project focuses on how systems behave under **real-time data flow, failure conditions, and operational pressure** — not just how they are deployed.

---

## ⚡ Why This Matters (Trading Context)

In trading systems:

- Latency directly impacts execution quality  
- Stale data introduces financial risk  
- Silent failures are more dangerous than outages  
- Recovery speed matters more than uptime metrics  

This project is built to model those realities.

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

## 🔁 Data Flow (Execution-Oriented View)

1. Market data service publishes price updates  
2. Kafka distributes events asynchronously  
3. Strategy engine consumes and processes data  
4. API exposes system state for downstream consumers  
5. Observability stack tracks latency, throughput, and freshness  

---

## ⚙️ Core Components

### Market Data Service (Python)
- Simulates live market data feed  
- Publishes events into Kafka  

### Kafka Broker
- Central event distribution layer  
- Enables decoupled processing  

### Strategy Engine (C# / .NET)
- Consumes and processes market data  
- Produces derived signals and metrics  

### API Gateway (FastAPI)
- Provides access to system state  
- Aggregates downstream outputs  

### Observability Stack
- Prometheus for metrics  
- Grafana for visualization  

---

## 🚨 Failure Scenarios

- Kafka broker outage  
- Consumer lag and backlog  
- Strategy engine degradation  
- API latency spikes  
- Stale data conditions  
- Partial system failure  

---

## 🔍 Observability Strategy

Key signals:

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

## 📂 Project Structure

.
├── api/
├── strategy/
├── market-data/
├── monitoring/
├── infra/
├── tools/
├── docs/
├── scripts/
└── docker-compose.yml

---

## ▶️ Running Locally

docker compose up --build

API → http://localhost:8000  
Prometheus → http://localhost:9090  
Grafana → http://localhost:3000  

---

## ☁️ Infrastructure

Terraform configs included for AWS ECS Fargate.

---

## 🧪 Reliability Engineering Focus

- System behavior under failure  
- Dependency-aware debugging  
- Latency analysis  
- Recovery workflows  

---

## 🧭 Roadmap

- Latency metrics  
- Kafka lag dashboards  
- Synthetic health checks  
- Failure injection  
- Network degradation testing  
- Distributed tracing  

---

## 💬 Interview Positioning

Built a simulated market data platform to model real-time data flow, system dependencies, and failure scenarios — focusing on latency, observability, and recovery.

---

## 📌 Author

Tim Heverin  
Chicago, IL
