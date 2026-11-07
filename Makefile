
# ==========================================================
# Trading Observability Platform — Control Plane
# ==========================================================
#
# Workloads:
#   - Python FastAPI market-data service
#   - Apache Kafka / ZooKeeper
#   - .NET strategy engine
#   - Python API gateway
#   - Web frontend
#   - Reliability probe
#
# Observability:
#   - Prometheus (metrics and alerting)
#   - Grafana (dashboards and exploration)
#   - Grafana Alloy (OpenTelemetry collector)
#   - Grafana Tempo (distributed tracing)
#   - Wacker-Watch (eBPF kernel telemetry)
#
# The eBPF agent requires native Linux and appropriate
# kernel privileges. It is disabled by default.
#
# ==========================================================

.DEFAULT_GOAL := help

COMPOSE := docker compose \
	-f docker-compose.yml \
	-f docker-compose.observability.yml

AGENT_DIR    := agents/wacker-watch
AGENT_SCRIPT := $(AGENT_DIR)/cmd/wacker_watch.py

ALLOY_IMAGE := grafana/alloy:v1.21.3
CURL_IMAGE  := curlimages/curl:latest
PROM_IMAGE  := prom/prometheus:v3.15.1

ALLOY_CONFIG := monitoring/alloy/config.alloy
TEMPO_CONFIG := monitoring/tempo/tempo.yaml

# ----------------------------------------------------------
# PHONY TARGETS
# ----------------------------------------------------------

.PHONY: help setup up down restart logs ps \
	doctor doctor-vm test validate clean \
	agent-deps agent-run agent-smoke agent-stress \
	agent-up agent-down \
	otel-up otel-down otel-restart otel-logs \
	otel-ps otel-check otel-validate \
	otel-status otel-config \
	test-unit test-rules test-failures reliability-check \
	incident test-persistence acceptance \
	test-replay test-correctness priority2-acceptance

# ==========================================================
# HELP
# ==========================================================

help:
	@echo ""
	@echo "=============================================="
	@echo " Trading Observability Platform"
	@echo "=============================================="
	@echo ""
	@echo "CORE LIFECYCLE"
	@echo "  make setup        Create local credentials"
	@echo "  make up           Build and start full platform"
	@echo "  make down         Stop platform (preserve volumes)"
	@echo "  make restart      Restart existing containers"
	@echo "  make ps           Show platform containers"
	@echo "  make logs         Tail platform logs"
	@echo ""
	@echo "OPENTELEMETRY / GRAFANA"
	@echo "  make otel-up       Start Alloy and Tempo"
	@echo "  make otel-down     Stop Alloy and Tempo"
	@echo "  make otel-restart  Restart Alloy and Tempo"
	@echo "  make otel-ps       Show observability containers"
	@echo "  make otel-logs     Tail Alloy and Tempo logs"
	@echo "  make otel-check    Check Alloy and Tempo health"
	@echo "  make otel-status   Show health and container state"
	@echo "  make otel-validate Validate Alloy and Compose"
	@echo "  make otel-config   Display Alloy configuration"
	@echo ""
	@echo "HEALTH AND VALIDATION"
	@echo "  make doctor       Run health checks"
	@echo "  make doctor-vm    Run VM diagnostics"
	@echo "  make test         Run smoke tests"
	@echo "  make validate     Run static validation"
	@echo "  make test-unit    Run Python and .NET unit tests"
	@echo "  make test-rules   Validate Prometheus rules"
	@echo "  make test-tracing Validate live distributed tracing"
	@echo "  make test-failures Run failure suite"
	@echo "  make reliability-check Run unit and rule tests"
	@echo ""
	@echo "RELIABILITY / ACCEPTANCE"
	@echo "  make incident     Run incident demonstration"
	@echo "  make test-persistence Verify persistent state"
	@echo "  make test-replay  Run replay verification"
	@echo "  make test-correctness Run correctness tests"
	@echo "  make acceptance   Run acceptance workflow"
	@echo "  make priority2-acceptance Full acceptance"
	@echo ""
	@echo "WACKER-WATCH eBPF"
	@echo "  make agent-deps   Install eBPF dependencies"
	@echo "  make agent-run    Run agent on Linux host"
	@echo "  make agent-up     Start containerized agent"
	@echo "  make agent-down   Stop containerized agent"
	@echo "  make agent-smoke  Run agent smoke tests"
	@echo "  make agent-stress Generate CPU scheduler load"
	@echo ""
	@echo "ACCESS POINTS"
	@echo "  Frontend   http://localhost:8082"
	@echo "  API        http://localhost:8000"
	@echo "  Prometheus http://localhost:9090"
	@echo "  Grafana    Port 3000 (configured host binding)"
	@echo "  Kafka UI   http://localhost:8081"
	@echo "  Alloy UI   http://localhost:12345"
	@echo "  OTLP gRPC  localhost:4317"
	@echo "  OTLP HTTP  localhost:4318"
	@echo "  Tempo      Internal Docker network: tempo:3200"
	@echo ""
	@echo "CLEANUP"
	@echo "  make clean        Destructive cleanup (confirmation)"
	@echo ""

# ==========================================================
# CORE LIFECYCLE
# ==========================================================

setup:
	@python3 scripts/setup-local.py

up: setup
	@echo "Starting complete trading platform..."
	$(COMPOSE) up -d --build

down:
	@echo "Stopping trading platform..."
	$(COMPOSE) down

# Restart running services without tearing down volumes
# or recreating the Kafka / observability stack.
# Use 'make up' to apply Compose configuration changes.
restart:
	@echo "Restarting existing platform containers..."
	$(COMPOSE) restart

# ==========================================================
# DEBUGGING
# ==========================================================

logs:
	@echo "Tailing platform logs..."
	$(COMPOSE) logs -f --tail=100

ps:
	@echo "Platform container status..."
	$(COMPOSE) ps

# ==========================================================
# HEALTH AND VALIDATION
# ==========================================================

doctor:
	@echo "Running system health checks..."
	@bash scripts/health-check.sh

doctor-vm:
	@echo "Running VM diagnostics..."
	@bash tools/vm-doctor/vm_doctor.sh

test:
	@echo "Running smoke tests..."
	@bash scripts/smoke-test.sh

validate: setup
	@echo "Validating Docker Compose configuration..."
	@$(COMPOSE) config --quiet
	@echo "OK: Docker Compose"
	@echo ""
	@echo "Compiling Python sources..."
	@python3 -m compileall -q \
		services scripts tools $(AGENT_DIR)/cmd
	@echo "OK: Python"
	@echo ""
	@echo "Checking shell scripts..."
	@if command -v shellcheck >/dev/null 2>&1; then \
		shellcheck -S warning scripts/*.sh && \
		echo "OK: ShellCheck"; \
	else \
		echo "SKIP: shellcheck not installed"; \
	fi
	@echo ""
	@echo "Checking Terraform formatting..."
	@if command -v terraform >/dev/null 2>&1; then \
		terraform -chdir=infra/terraform/envs/aws-managed \
			fmt -check -recursive && \
		echo "OK: Terraform formatting"; \
	else \
		echo "SKIP: terraform not installed"; \
	fi

# ==========================================================
# OPENTELEMETRY / GRAFANA ALLOY / TEMPO
# ==========================================================

# Start only the telemetry pipeline.
# Do not start or recreate application dependencies.

otel-up:
	@echo "Starting Grafana Alloy and Tempo..."
	$(COMPOSE) up -d --no-deps tempo alloy
	@echo "Observability services started."

# Stop containers without removing persistent volumes.

otel-down:
	@echo "Stopping Grafana Alloy and Tempo..."
	$(COMPOSE) stop alloy tempo

# Restart without container recreation.
# Use otel-up to apply Compose specification changes.

otel-restart:
	@echo "Restarting observability services..."
	$(COMPOSE) restart tempo alloy

otel-logs:
	@echo "Streaming Alloy and Tempo logs..."
	$(COMPOSE) logs -f --tail=100 alloy tempo

otel-ps:
	@echo "Observability container status..."
	$(COMPOSE) ps alloy tempo

# ----------------------------------------------------------
# OpenTelemetry health checks
# ----------------------------------------------------------

otel-check:
	@set -eu; \
	echo "Checking Grafana Alloy readiness..."; \
	curl -fsS http://127.0.0.1:12345/-/ready; \
	echo ""; \
	echo "OK: Alloy ready"; \
	echo ""; \
	echo "Checking Grafana Tempo readiness..."; \
	network=$$(docker inspect mdp-tempo \
		--format '{{range $$name, $$network := .NetworkSettings.Networks}}{{println $$name}}{{end}}' \
		| head -n 1); \
	test -n "$$network" || { \
		echo "ERROR: Tempo Docker network not found"; \
		exit 1; \
	}; \
	docker run --rm \
		--network "$$network" \
		$(CURL_IMAGE) \
		-fsS http://tempo:3200/ready; \
	echo ""; \
	echo "OK: Tempo ready"; \
	echo ""; \
	echo "All observability readiness checks passed."

# ----------------------------------------------------------
# Observability status
# ----------------------------------------------------------

otel-status:
	@echo "=============================================="
	@echo " OpenTelemetry Stack Status"
	@echo "=============================================="
	@echo ""
	@$(COMPOSE) ps alloy tempo
	@echo ""
	@$(MAKE) --no-print-directory otel-check

# ----------------------------------------------------------
# Configuration validation
# ----------------------------------------------------------

otel-validate:
	@echo "Validating Docker Compose..."
	@$(COMPOSE) config --quiet
	@echo "OK: Docker Compose"
	@echo ""
	@echo "Validating Grafana Alloy..."
	@docker run --rm \
		-v "$(CURDIR)/$(ALLOY_CONFIG):/etc/alloy/config.alloy:ro" \
		$(ALLOY_IMAGE) \
		validate /etc/alloy/config.alloy
	@echo "OK: Grafana Alloy"
	@echo ""
	@echo "Checking Tempo configuration file..."
	@test -s "$(TEMPO_CONFIG)" || { \
		echo "ERROR: Tempo configuration missing or empty"; \
		exit 1; \
	}
	@echo "OK: Tempo configuration present"
	@echo ""
	@echo "Observability static validation passed."
	@echo "NOTE: Tempo schema and readiness require runtime checks."

otel-config:
	@echo "Grafana Alloy configuration:"
	@echo "----------------------------------------------"
	@cat $(ALLOY_CONFIG)

# ==========================================================
# WACKER-WATCH eBPF AGENT
# ==========================================================

agent-deps:
	@echo "Installing BCC and eBPF dependencies..."
	sudo apt update
	@echo "BCC Python bindings come from python3-bpfcc."
	sudo apt install -y \
		bpfcc-tools \
		libbpfcc-dev \
		python3-bpfcc \
		linux-tools-common \
		linux-tools-generic \
		llvm \
		clang \
		python3-pip \
		stress-ng
	sudo pip3 install --break-system-packages \
		prometheus_client

agent-run:
	@echo "Launching Wacker-Watch on host..."
	sudo python3 $(AGENT_SCRIPT)

agent-stress:
	@echo "Generating CPU scheduler stress..."
	stress-ng --schedmix 4 \
		--timeout 10s \
		--metrics-brief

agent-up:
	@echo "Starting containerized Wacker-Watch..."
	$(COMPOSE) --profile ebpf up -d --build wacker-watch

agent-down:
	@echo "Stopping Wacker-Watch..."
	$(COMPOSE) --profile ebpf stop wacker-watch

agent-smoke:
	@echo "Running Wacker-Watch smoke tests..."
	@bash scripts/wacker-watch-smoke-test.sh

# ==========================================================
# UNIT / RELIABILITY TESTING
# ==========================================================

test-unit:
	@echo "Running Python unit tests..."
	python3 -m pytest tests
	@echo "Running .NET tests..."
	dotnet test services/strategy-csharp/tests

test-rules:
	@echo "Checking Prometheus alert rules..."
	docker run --rm \
		--entrypoint promtool \
		-v "$(CURDIR)/monitoring/prometheus:/etc/prometheus:ro" \
		-w /etc/prometheus \
		$(PROM_IMAGE) \
		check rules alerts.yml slo.yml

	@echo "Running Prometheus rule tests..."
	docker run --rm \
		--entrypoint promtool \
		-v "$(CURDIR)/monitoring/prometheus:/etc/prometheus:ro" \
		-w /etc/prometheus \
		$(PROM_IMAGE) \
		test rules slo.test.yml

test-failures:
	@echo "Running failure injection suite..."
	python3 scripts/failure-suite.py all

reliability-check: test-unit test-rules
	@echo "Reliability checks completed."

# ==========================================================
# INCIDENT VALIDATION
# ==========================================================

incident:
	@echo "Running incident demonstration..."
	@bash scripts/demo-incident.sh

test-persistence:
	@echo "Verifying persistent state..."
	python3 scripts/verify-persistence.py

# ==========================================================
# ACCEPTANCE WORKFLOWS
# ==========================================================

acceptance: up
	@echo "Running complete acceptance workflow..."
	python3 scripts/verify-pipeline.py
	bash scripts/health-check.sh
	bash scripts/smoke-test.sh
	python3 scripts/failure-suite.py consumer
	python3 scripts/verify-persistence.py
	python3 scripts/verify-pipeline.py
	bash scripts/health-check.sh

test-replay: setup
	@echo "Running replay verification..."
	python3 scripts/replay-check.py

test-correctness:
	@echo "Running correctness suite..."
	python3 scripts/correctness-suite.py --boundary before
	python3 scripts/correctness-suite.py --boundary after

priority2-acceptance: acceptance
	@echo "Running Priority 2 acceptance..."
	python3 scripts/replay-check.py
	python3 scripts/correctness-suite.py --boundary before
	python3 scripts/correctness-suite.py --boundary after
	python3 scripts/verify-pipeline.py

# ==========================================================
# CLEANUP
# ==========================================================

# WARNING:
# This operation deletes Compose-managed Docker volumes.
# That includes persistent Kafka, Grafana, Prometheus,
# Tempo, application state, and ZooKeeper data.
#
# Regular shutdown:
#   make down
#
# Destructive cleanup:
#   make clean

clean:
	@echo ""
	@echo "WARNING: DESTRUCTIVE CLEANUP"
	@echo ""
	@echo "This will remove Compose-managed containers"
	@echo "AND their named volumes."
	@echo ""
	@printf "Type DELETE to confirm: "; \
	read confirm; \
	if [ "$$confirm" != "DELETE" ]; then \
		echo "Cleanup cancelled."; \
		exit 1; \
	fi
	@echo "Removing containers and volumes..."
	$(COMPOSE) --profile ebpf down -v
	@echo "Removing Python cache files..."
	@find . -type d -name "__pycache__" \
		-prune -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" \
		-delete 2>/dev/null || true
	@echo "Cleanup completed."


# ==========================================================
# DISTRIBUTED TRACING VALIDATION
# ==========================================================

.PHONY: test-tracing

test-tracing:
	@python3 scripts/trace-validation.py
