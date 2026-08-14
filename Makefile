.PHONY: help install install-dbt lint format typecheck test backfill dbt-build dbt-docs pg-up pg-down check

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install package with dev dependencies
	pip install -e ".[dev]"

install-dbt: ## Install package with dbt dependencies
	pip install -e ".[dbt]"

lint: ## Run ruff lint and format checks
	ruff check .
	ruff format --check .

format: ## Auto-format and auto-fix with ruff
	ruff format .
	ruff check --fix .

typecheck: ## Run mypy type checks
	mypy ingestion tests

test: ## Run the test suite
	pytest -q

backfill: ## Backfill seasons 2018 through 2024
	python -m ingestion.cli backfill --from 2018 --to 2024

dbt-build: ## Build the dbt project (dev target)
	dbt build --project-dir warehouse/dbt --profiles-dir warehouse/dbt --target dev

dbt-docs: ## Generate dbt docs (dev target)
	dbt docs generate --project-dir warehouse/dbt --profiles-dir warehouse/dbt --target dev

pg-up: ## Start the postgres container
	docker compose up -d postgres

pg-down: ## Stop compose services
	docker compose down

check: lint typecheck test ## Run lint, typecheck and tests
