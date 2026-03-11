.PHONY: help mig build up down restart logs shell db-shell redis-shell test clean dev prod createsuperuser listowners changepassword

# ===========================================
# Help
# ===========================================
help:
	@echo "S1P - Available Commands"
	@echo ""
	@echo "Local Development:"
	@echo "  make mig          - Create and run database migrations"
	@echo "  make run          - Run the application locally"
	@echo "  make test         - Run tests"
	@echo ""
	@echo "Docker Commands:"
	@echo "  make build        - Build Docker images"
	@echo "  make up           - Start all services"
	@echo "  make down         - Stop all services"
	@echo "  make restart      - Restart all services"
	@echo "  make logs         - View application logs"
	@echo "  make logs-all     - View all service logs"
	@echo ""
	@echo "Docker Development:"
	@echo "  make dev          - Start with dev tools (pgadmin, redis-commander)"
	@echo "  make dev-down     - Stop dev environment"
	@echo ""
	@echo "Shell Access:"
	@echo "  make shell        - Open shell in app container"
	@echo "  make db-shell     - Open PostgreSQL shell"
	@echo "  make redis-shell  - Open Redis CLI"
	@echo ""
	@echo "Database:"
	@echo "  make db-migrate   - Run migrations in container"
	@echo "  make db-reset     - Reset database (WARNING: destroys data)"
	@echo ""
	@echo "Management:"
	@echo "  make createsuperuser - Create a new owner account"
	@echo "  make listowners      - List all owner accounts"
	@echo "  make changepassword  - Change owner password (email=...)"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean        - Remove containers and volumes"
	@echo "  make clean-all    - Remove everything including images"

# ===========================================
# Local Development
# ===========================================
mig:
	alembic revision --autogenerate -m "mig"
	alembic upgrade head

run:
	uvicorn main:app --reload --host 0.0.0.0 --port 8000

test:
	python -m pytest source/tests/ -v --tb=short

# ===========================================
# Management Commands
# ===========================================
createsuperuser:
	docker compose exec app python manage.py createsuperuser

listowners:
	docker compose exec app python manage.py listowners

changepassword:
	docker compose exec app python manage.py changepassword $(email)

# ===========================================
# Docker Build
# ===========================================
build:
	docker compose build

build-no-cache:
	docker compose build --no-cache

# ===========================================
# Docker Run
# ===========================================
up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

# Development mode with pgadmin and redis-commander
dev:
	docker compose --profile dev up -d

dev-down:
	docker compose --profile dev down

# Production mode (minimal services)
prod:
	docker compose up -d app db redis

# ===========================================
# Logs
# ===========================================
logs:
	docker compose logs -f app

logs-all:
	docker compose logs -f

logs-db:
	docker compose logs -f db

logs-redis:
	docker compose logs -f redis

# ===========================================
# Shell Access
# ===========================================
shell:
	docker compose exec app bash

db-shell:
	docker compose exec db psql -U $${POSTGRES_USER:-postgres} -d $${POSTGRES_DB:-sip_tools}

redis-shell:
	docker compose exec redis redis-cli

# ===========================================
# Database Management
# ===========================================
db-migrate:
	docker compose exec app alembic upgrade head

db-migrate-create:
	docker compose exec app alembic revision --autogenerate -m "$(msg)"

db-downgrade:
	docker compose exec app alembic downgrade -1

db-reset:
	@echo "WARNING: This will destroy all data in the database!"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ]
	docker compose down -v
	docker compose up -d db
	@sleep 5
	docker compose up -d app

# ===========================================
# Health Checks
# ===========================================
health:
	@echo "Checking services health..."
	@docker compose ps
	@echo ""
	@echo "App health:"
	@curl -s http://localhost:8000/ | head -c 200 || echo "App not responding"
	@echo ""
	@echo "Database:"
	@docker compose exec -T db pg_isready -U postgres || echo "DB not ready"
	@echo ""
	@echo "Redis:"
	@docker compose exec -T redis redis-cli ping || echo "Redis not ready"

# ===========================================
# Cleanup
# ===========================================
clean:
	docker compose down -v --remove-orphans

clean-all:
	docker compose down -v --remove-orphans --rmi all

prune:
	docker system prune -f
	docker volume prune -f

# ===========================================
# Utility
# ===========================================
ps:
	docker compose ps

stats:
	docker stats s1p-api s1p-db s1p-redis
