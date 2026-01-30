.PHONY: help install start stop logs clean test lint format migration upgrade

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install Python dependencies
	pip install -r requirements.txt
	pip install -e ".[dev]"

start: ## Start all services with Docker Compose
	cd deploy && docker compose up -d

stop: ## Stop all services
	cd deploy && docker compose down

restart: ## Restart all services
	cd deploy && docker compose restart

logs: ## Show logs for all services
	cd deploy && docker compose logs -f

logs-api: ## Show logs for web API
	cd deploy && docker compose logs -f web_api

logs-worker: ## Show logs for worker
	cd deploy && docker compose logs -f worker_ingest

clean: ## Stop services and remove volumes (WARNING: deletes data)
	cd deploy && docker compose down -v

ps: ## Show service status
	cd deploy && docker compose ps

test: ## Run tests
	pytest tests/

lint: ## Run linters
	ruff check .

format: ## Format code with black
	black .

check: format lint ## Format and lint code

migration: ## Create new Alembic migration
	@read -p "Enter migration name: " name; \
	alembic revision --autogenerate -m "$$name"

upgrade: ## Run database migrations
	alembic upgrade head

downgrade: ## Rollback last migration
	alembic downgrade -1

shell-api: ## Open shell in web_api container
	cd deploy && docker compose exec web_api bash

shell-worker: ## Open shell in worker_ingest container
	cd deploy && docker compose exec worker_ingest bash

shell-db: ## Open PostgreSQL shell
	cd deploy && docker compose exec postgres psql -U bench_user -d ai_knowledge_bench

build: ## Build Docker images
	cd deploy && docker compose build

rebuild: ## Rebuild Docker images without cache
	cd deploy && docker compose build --no-cache

eval: ## Run evaluation (requires active chunk profile)
	@echo "Get active chunk profile ID first:"
	@echo "curl http://localhost:8080/v1/chunk-profiles | jq '.[] | select(.is_active==true) | .id'"
	@read -p "Enter chunk profile ID: " profile; \
	python -m packages.eval.run --dataset eval/golden_set_v1.jsonl --profile "$$profile" --topk 5

dev: ## Start development environment
	@echo "Starting services..."
	make start
	@echo ""
	@echo "Waiting for services to be ready..."
	@sleep 10
	@echo ""
	@echo "✅ Development environment ready!"
	@echo "   - Web UI: http://localhost:8080"
	@echo "   - API Docs: http://localhost:8080/docs"
	@echo ""
	@echo "💡 Quick commands:"
	@echo "   make logs        - View all logs"
	@echo "   make logs-api    - View API logs"
	@echo "   make logs-worker - View worker logs"
	@echo "   make stop        - Stop services"
