# Market Data Trading Platform

[![CI](https://github.com/dj-3dub/market-data-trading-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/dj-3dub/market-data-trading-platform/actions/workflows/ci.yml)

A fully containerized microservices project showcasing DevOps engineering skills with Docker, Python, C#, Kafka, Prometheus, Grafana, and Terraform.

This platform simulates a small trading system with:

- A **market data service** that publishes streaming price data  
- A **strategy engine** written in C# that consumes data and exposes metrics  
- An **API gateway** (FastAPI) that fronts the services  
- A **web frontend** that visualizes the data  
- **Kafka** for streaming  
- **Prometheus + Grafana** for observability  
- **Terraform** for ECS Fargate infrastructure (designed for offline validation today)

---

## 🏗️ Architecture Overview
# Architecture

![Market Data Trading Platform Architecture](architecture.png)


The system is split into several services:

### **market-data-python**
Python/FastAPI service that simulates market data updates and exposes Prometheus metrics.

### **strategy-csharp**
C#/.NET 9 service that ingests market data, runs a simple trading strategy, and exports detailed runtime/strategy metrics.

### **api-gateway-python**
Python/FastAPI API gateway that aggregates data from backend services and provides a unified HTTP interface.

### **web-frontend**
Web UI (containerized) that displays current market data and strategy outputs.

### **Kafka + Zookeeper**
Provides the event stream between services (e.g., prices, events).

### **Prometheus + Grafana**
Full observability stack with metrics scraping and dashboards.

### **Terraform (infra/terraform/envs/aws-fargate)**
ECS Fargate configuration for running the core services in AWS (cluster, task definitions, services, log group, security group).  
> Note: The provider is currently set up for *offline validation* (no real AWS creds). Applying this config to AWS would require valid credentials.

Architecture docs:

- `docs/architecture.md`
- `docs/architecture.dot`

---

## 🚀 Running the Stack Locally

Requirements:

- Docker & Docker Compose
- Git

Clone and start:

```bash
git clone https://github.com/dj-3dub/market-data-trading-platform.git
cd market-data-trading-platform
docker compose up -d
```

Services:

- Web UI: `http://<host>:8080`
- API Gateway: `http://<host>:8000`
- Prometheus: `http://<host>:9091`
- Grafana: `http://<host>:3000` (default: admin/admin)

---

## 🧰 Ops Toolbox

This project includes a suite of diagnostic tools used to operate, troubleshoot, and validate the platform.

---

### 🔧 VM Doctor

Full system health check:

- CPU load  
- RAM availability  
- Swap usage  
- Disk usage  
- Docker container resource usage  
- Top processes  
- OK / WARN / CRIT indicators  

Run:

```bash
make doctor-vm
```

Located in `tools/vm-doctor/vm_doctor.sh`.

---

### 📈 Prometheus Doctor

Checks Prometheus health and target ingestion:

- API availability  
- Active targets  
- `up` status  
- Missing metrics  
- Missing scrape jobs  

Run:

```bash
python3 tools/prometheus-doctor/prometheus_doctor.py
```

Located in `tools/prometheus-doctor/prometheus_doctor.py`.

---

### 🟦 .NET Doctor (planned)

Will diagnose .NET SDK environments, workloads, runtimes, and container builds.

---

### 🐳 Future Tools

- Docker health/liveness probe tester  
- Port readiness validator  
- API smoke-test suite  

---

## 🚦 CI/CD Pipeline

A GitHub Actions workflow validates the entire platform on every push and PR.

### Pipeline includes:

### **Docker Build Validation**
Builds:

- `market-data-python`
- `api-gateway-python`
- `web-frontend`

### **.NET Strategy Engine Build**
Restores & compiles `.NET 9` C# code.

### **Terraform Validation**
Runs:

- `terraform fmt -check`
- `terraform validate`  
  (offline mode; no real AWS credentials required)

Workflow file:

```
.github/workflows/ci.yml
```

---

## 🧱 Project Layout

```
services/
  market-data-python/
  api-gateway-python/
  strategy-csharp/
  web-frontend/

monitoring/
  prometheus/
  grafana/

infra/
  terraform/
    envs/
      aws-fargate/

tools/
  vm-doctor/
  prometheus-doctor/

docs/
  architecture.md
  architecture.dot

docker-compose.yml
Makefile
README.md
```

---

## 🔮 Future Improvements

- Unit/integration tests (Python + C#)  
- Terraform expansion (ALB, Route 53, Secrets Manager)  
- Grafana alerting  
- Additional exporters  
- CI test matrix  

---

## 📄 License

MIT or Apache 2.0 (optional — choose if you add one)
