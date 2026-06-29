# Self-documenting Makefile. Run `make` or `make help` to list targets.
# Each target's `## comment` is parsed into the help output.

IMAGE ?= fintual-content-service
TAG   ?= local
COMPOSE ?= docker compose

.DEFAULT_GOAL := help

.PHONY: help up down seed dev test lint fmt bench build logs

help: ## Show this help
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

up: ## Start the full stack (db -> migrate -> web) in the background
	$(COMPOSE) up --build -d

down: ## Stop the stack and remove volumes (wipes the dev DB)
	$(COMPOSE) down -v

dev: ## Start the stack in the foreground (live logs, --reload web)
	$(COMPOSE) up --build

seed: ## Load demo data into the running DB
	$(COMPOSE) run --rm web python manage.py seed

logs: ## Tail logs from all services
	$(COMPOSE) logs -f

build: ## Build the production Docker image ($(IMAGE):$(TAG))
	docker build -t $(IMAGE):$(TAG) .

test: ## Run the pytest suite (locally, via uv)
	uv run pytest -q

lint: ## Run ruff lint + format check (no changes written)
	uv run ruff check .
	uv run ruff format --check .

fmt: ## Auto-fix lint issues and format the code
	uv run ruff check --fix .
	uv run ruff format .

bench: ## Run the per-endpoint benchmark harness (counts SQL queries + latency)
	uv run python benchmarks/bench.py
