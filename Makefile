# ==========================================================
# 🛠️ Market Data Trading Platform — Control Plane
# ==========================================================

.PHONY: help up down restart logs ps doctor doctor-vm test clean

# ----------------------------------------------------------
# 📖 Help
# ----------------------------------------------------------
help:
	@echo ""
	@echo "📊 Trading Platform Makefile"
	@echo ""
	@echo "Core Commands:"
	@echo "  make up        → Start all services"
	@echo "  make down      → Stop all services"
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
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean     → Remove containers/volumes"
	@echo ""

# ----------------------------------------------------------
# 🚀 Core Lifecycle
# ----------------------------------------------------------
up:
	@echo "🚀 Starting trading platform..."
	docker compose up -d --build

down:
	@echo "🛑 Stopping trading platform..."
	docker compose down

restart: down up

# ----------------------------------------------------------
# 🔍 Debugging
# ----------------------------------------------------------
logs:
	@echo "📜 Tailing logs..."
	docker compose logs -f --tail=100

ps:
	@echo "📦 Running containers..."
	docker compose ps

# ----------------------------------------------------------
# 🧠 Health & Validation
# ----------------------------------------------------------
doctor: doctor-vm
	@echo "🩺 Running system health checks..."
	@bash scripts/placeholders/health-check.sh || true

doctor-vm:
	@echo "🖥️ Running VM Doctor..."
	@bash tools/vm-doctor/vm_doctor.sh

test:
	@echo "🧪 Running smoke tests..."
	@bash scripts/placeholders/smoke-test.sh || true

# ----------------------------------------------------------
# 🧹 Cleanup
# ----------------------------------------------------------
clean:
	@echo "🧹 Cleaning environment..."
	docker compose down -v
	docker system prune -f
