
# Market Data Trading Platform

A fully containerized microservices project showcasing DevOps engineering skills with Docker, Python, C#, Kafka, Prometheus, Grafana, and Terraform.

This platform simulates a market data feed, strategy engine, and API gateway—instrumented end-to-end with observability tools and streaming infrastructure.

---

# 🧰 Ops Toolbox

This project includes a suite of diagnostic and observability tools designed to help troubleshoot performance issues, validate monitoring configurations, and keep the platform running smoothly. These tools demonstrate practical DevOps workflows and can be executed using Makefile shortcuts or direct CLI calls.

---

## 🔧 VM Doctor
A full system health check for your VM. Provides detailed analysis of:

- CPU load (per core)
- RAM availability
- Swap usage
- Disk usage & I/O saturation
- Docker container CPU & memory usage
- Top processes by memory
- Summary with OK / WARN / CRIT indicators

**Run it:**

```bash
make doctor-vm
```

Script location: `tools/vm-doctor/vm_doctor.sh`

---

## 📈 Prometheus Doctor
Validates Prometheus health and metrics ingestion:

- Confirms Prometheus API availability
- Lists all activeTargets
- Verifies `up` status for required jobs
- Checks presence of key metrics coming from services
- Detects missing scrape jobs or misconfigured exporters

**Run it:**

```bash
python3 tools/prometheus-doctor/prometheus_doctor.py
```

Script location: `tools/prometheus-doctor/prometheus_doctor.py`

---

## 🟦 .NET Doctor
Used to troubleshoot .NET SDK issues inside Docker or the VM environment:

- Validates .NET installation
- Checks workloads & SDKs
- Detects missing runtime packs
- Prints actionable error messages

**Run it:**

```bash
dotnet run --project tools/dotnet-doctor
```

---

## 🐳 Container Health Tools (coming soon)
Future additions will include:

- Docker health probe tester
- Port and readiness probe validator
- API smoke test suite

---

## Summary

These tools provide a real-world operational toolkit similar to what engineers use when supporting production microservices. They’re especially valuable for:

- Home lab reliability
- CI/CD validation
- Demonstrating DevOps troubleshooting workflows
