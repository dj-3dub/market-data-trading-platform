# ==========================================================
# 🛠️ Trading Observability Platform — Control Plane
# ==========================================================
# Unifies the trading platform workload with the Wacker-Watch eBPF agent.
# One Prometheus, one Grafana, two signal sources:
#   - application signal : market data, strategy, API, Kafka
#   - kernel signal      : off-CPU duration (eBPF)

COMPOSE      := docker compose
AGENT_DIR    := agents/wacker-watch
AGENT_SCRIPT := $(AGENT_DIR)/cmd/wacker_watch.py

.PHONY: help setup up down restart logs ps doctor doctor-vm test clean \
        agent-deps agent-run agent-smoke agent-stress agent-up agent-down \
        validate

# ----------------------------------------------------------
# 📖 Help
# ----------------------------------------------------------
help:
	@echo ""
	@echo "📊 Trading Observability Platform Makefile"
	@echo ""
	@echo "Core Commands:"
	@echo "  make setup     → Create local Grafana credentials (preserves existing password)"
	@echo "  make up        → Start the platform (app + observability)"
	@echo "  make down      → Stop the platform"
	@echo "  make restart   → Restart platform"
	@echo ""
	@echo "Debugging:"
	@echo "  make logs      → Tail logs"
	@echo "  make ps        → Show containers"
	@echo ""
	@echo "Health & Testing:"
	@echo "  make doctor    → Run all health checks"
	@echo "  make doctor-vm → Run VM diagnostics"
	@echo "  make test      → Run smoke tests"
	@echo "  make incident  → Verify consumer outage, alerting, and recovery"
	@echo "  make test-persistence → Verify records, offsets and monitoring state survive recreation"
	@echo "  make priority2-acceptance → Run complete correctness and recovery acceptance"
	@echo "  make acceptance → Build and run the complete local acceptance workflow"
	@echo "  make validate  → Static checks (compose, python, shell, terraform)"
	@echo ""
	@echo "Wacker-Watch eBPF Agent (requires native Linux + sudo):"
	@echo "  make agent-deps   → Install BCC / eBPF tooling dependencies"
	@echo "  make agent-run    → Run the collector on the host"
	@echo "  make agent-up     → Start the agent as a container (profile: ebpf)"
	@echo "  make agent-down   → Stop the agent container"
	@echo "  make agent-stress → Simulate a CPU micro-burst with stress-ng"
	@echo "  make agent-smoke  → Run agent smoke tests"
	@echo ""
	@echo "Access Points (override with e.g. WEB_PORT=8082 make up):"
	@echo "  Frontend   → http://localhost:8082    (WEB_PORT)"
	@echo "  API        → http://localhost:8000    (API_PORT)"
	@echo "  Agent      → http://localhost:8001    (AGENT_PORT)"
	@echo "  Prometheus → http://localhost:9090    (PROMETHEUS_PORT)"
	@echo "  Grafana    → http://localhost:3000    (GRAFANA_PORT, password in .env)"
	@echo "  Kafka UI   → http://localhost:8081    (KAFKA_UI_PORT)"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean     → Remove containers/volumes and build artifacts"
	@echo ""

# ----------------------------------------------------------
# 🚀 Core Lifecycle
# ----------------------------------------------------------
setup:
	@python3 scripts/setup-local.py

up: setup
	@echo "🚀 Starting trading observability platform..."
	$(COMPOSE) up -d --build

down:
	@echo "🛑 Stopping trading observability platform..."
	$(COMPOSE) down

restart: down up

# ----------------------------------------------------------
# 🔍 Debugging
# ----------------------------------------------------------
logs:
	@echo "📜 Tailing logs..."
	$(COMPOSE) logs -f --tail=100

ps:
	@echo "📦 Running containers..."
	$(COMPOSE) ps

# ----------------------------------------------------------
# 🧠 Health & Validation
# ----------------------------------------------------------
doctor:
	@echo "🩺 Running system health checks..."
	@bash scripts/health-check.sh

doctor-vm:
	@echo "🖥️ Running VM Doctor..."
	@bash tools/vm-doctor/vm_doctor.sh

test:
	@echo "🧪 Running smoke tests..."
	@bash scripts/smoke-test.sh

.PHONY: incident
incident:
	@bash scripts/demo-incident.sh

validate: setup
	@echo "🔍 Validating compose configuration..."
	@$(COMPOSE) config --quiet && echo "OK: docker-compose.yml"
	@echo "🔍 Compiling Python sources..."
	@python3 -m compileall -q services scripts tools $(AGENT_DIR)/cmd >/dev/null && echo "OK: python"
	@echo "🔍 Checking shell scripts..."
	@if command -v shellcheck >/dev/null; then \
		shellcheck -S warning scripts/*.sh && echo "OK: shellcheck"; \
	else echo "SKIP: shellcheck not installed"; fi
	@echo "🔍 Checking terraform formatting..."
	@if command -v terraform >/dev/null; then \
		terraform -chdir=infra/terraform/envs/aws-managed fmt -check -recursive && echo "OK: terraform fmt"; \
	else echo "SKIP: terraform not installed"; fi

# ----------------------------------------------------------
# ⏱️ Wacker-Watch eBPF Agent
# ----------------------------------------------------------
agent-deps:
	@echo "📦 Installing eBPF and BCC tooling dependencies..."
	sudo apt update
	@echo "   NOTE: BCC Python bindings come from the python3-bpfcc package."
	@echo "         The 'bcc' package on PyPI is unmaintained and does not build"
	@echo "         against modern Python (3.12+)."
	sudo apt install -y bpfcc-tools libbpfcc-dev python3-bpfcc \
		linux-tools-common linux-tools-generic \
		llvm clang python3-pip stress-ng
	sudo pip3 install --break-system-packages prometheus_client

agent-run:
	@echo "🚀 Launching Wacker-Watch into the Linux Kernel..."
	sudo python3 $(AGENT_SCRIPT)

agent-stress:
	@echo "💥 Simulating a 10-second micro-burst (CPU scheduler thrashing)..."
	stress-ng --schedmix 4 --timeout 10s --metrics-brief

agent-up:
	@echo "⏱️ Starting Wacker-Watch eBPF agent (requires native Linux + privileges)..."
	$(COMPOSE) --profile ebpf up -d --build wacker-watch

agent-down:
	@echo "🛑 Stopping Wacker-Watch eBPF agent..."
	$(COMPOSE) --profile ebpf stop wacker-watch

agent-smoke:
	@echo "🔎 Running Wacker-Watch smoke tests..."
	@bash scripts/wacker-watch-smoke-test.sh

# ----------------------------------------------------------
# 🧹 Cleanup
# ----------------------------------------------------------
clean:
	@echo "🧹 Cleaning environment..."
	$(COMPOSE) --profile ebpf down -v
	@echo "🧹 Removing Python cache files..."
	@find . -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	docker system prune -f
.PHONY: test-unit test-rules test-failures reliability-check
test-unit:
	python3 -m pytest tests
	dotnet test services/strategy-csharp/tests

test-rules:
	docker run --rm --entrypoint promtool -v "$(CURDIR)/monitoring/prometheus:/etc/prometheus:ro" -w /etc/prometheus prom/prometheus:v3.1.0 check rules alerts.yml slo.yml
	docker run --rm --entrypoint promtool -v "$(CURDIR)/monitoring/prometheus:/etc/prometheus:ro" -w /etc/prometheus prom/prometheus:v3.1.0 test rules slo.test.yml

test-failures:
	python3 scripts/failure-suite.py all

reliability-check: test-unit test-rules

.PHONY: test-persistence acceptance
test-persistence:
	python3 scripts/verify-persistence.py

acceptance: up
	python3 scripts/verify-pipeline.py
	bash scripts/health-check.sh
	bash scripts/smoke-test.sh
	python3 scripts/failure-suite.py consumer
	python3 scripts/verify-persistence.py
	python3 scripts/verify-pipeline.py
	bash scripts/health-check.sh

.PHONY: test-replay test-correctness priority2-acceptance
test-replay: setup
	python3 scripts/replay-check.py

test-correctness:
	python3 scripts/correctness-suite.py --boundary before
	python3 scripts/correctness-suite.py --boundary after

priority2-acceptance: acceptance
	python3 scripts/replay-check.py
	python3 scripts/correctness-suite.py --boundary before
	python3 scripts/correctness-suite.py --boundary after
	python3 scripts/verify-pipeline.py

# SRE portfolio drill: broker outage + post-recovery data integrity.
# The fault suite restores Kafka even on failure. Do not run on production.
.PHONY: sre-kafka-drill
sre-kafka-drill:
	python3 scripts/sre-kafka-drill.py
