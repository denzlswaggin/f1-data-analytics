.PHONY: help setup install install-dbt lock lint format typecheck test backfill dbt-build dbt-docs dbt-docs-check dashboard-snapshot dashboard-prepare dashboard-check dashboard-dev race-control-audit data-audit dagster dagster-validate pg-up pg-down prod-up prod-down prod-logs prod-smoke prod-backup prod-restore-drill prod-restore-drill-latest check

# Prefer the repository virtual environment without requiring it. CI and
# containers deliberately fall back to the Python found on PATH. Callers may
# still override this explicitly, for example: make PYTHON=python3.12 check.
PYTHON ?= $(firstword $(wildcard .venv/bin/python .venv/Scripts/python.exe) python)
PIP := $(PYTHON) -m pip
PYTHON_BIN := $(dir $(PYTHON))
DBT ?= $(if $(wildcard $(PYTHON_BIN)dbt),$(PYTHON_BIN)dbt,$(if $(wildcard $(PYTHON_BIN)dbt.exe),$(PYTHON_BIN)dbt.exe,dbt))
DAGSTER ?= $(if $(wildcard $(PYTHON_BIN)dagster),$(PYTHON_BIN)dagster,$(if $(wildcard $(PYTHON_BIN)dagster.exe),$(PYTHON_BIN)dagster.exe,dagster))

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install package with dev dependencies
	$(PIP) install -e ".[dev]"

setup: install ## Install Python and both dashboard workspaces from their locks
	npm --prefix dashboard ci
	npm --prefix web ci

install-dbt: ## Install package with dbt dependencies
	$(PIP) install -e ".[dbt]"

lock: ## Recompile pinned Python environments from pyproject.toml
	$(PYTHON) -m piptools compile --strip-extras --no-emit-index-url --output-file=requirements.lock pyproject.toml
	$(PYTHON) -m piptools compile --extra dev --extra orchestration --strip-extras --no-emit-index-url --output-file=requirements-ci.lock pyproject.toml
	$(PYTHON) -m piptools compile --extra dbt --strip-extras --no-emit-index-url --output-file=requirements-dbt.lock pyproject.toml
	$(PYTHON) -m piptools compile --extra telemetry --strip-extras --no-emit-index-url --output-file=requirements-telemetry.lock pyproject.toml

lint: ## Run ruff lint and format checks
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

format: ## Auto-format and auto-fix with ruff
	$(PYTHON) -m ruff format .
	$(PYTHON) -m ruff check --fix .

typecheck: ## Run mypy type checks
	$(PYTHON) -m mypy ingestion analytics orchestration tests

test: ## Run the test suite
	$(PYTHON) -m pytest -q

backfill: ## Backfill seasons 2006 through 2025 (the full driver-ratings dataset)
	$(PYTHON) -m ingestion.cli backfill --from 2006 --to 2025

dbt-build: ## Build the dbt project (dev target)
	$(DBT) build --project-dir warehouse/dbt --profiles-dir warehouse/dbt --target dev

dbt-docs: ## Generate dbt docs (dev target)
	$(DBT) docs generate --project-dir warehouse/dbt --profiles-dir warehouse/dbt --target dev

dbt-docs-check: dbt-docs ## Generate docs, then fail if any model/source lacks a description
	$(PYTHON) scripts/check_dbt_docs_coverage.py warehouse/dbt/target/manifest.json

dashboard-snapshot: ## Export a versioned, read-only Evidence database
	$(PYTHON) scripts/dashboard_snapshot.py build --output-dir data/dashboard

dashboard-prepare: ## Validate marts, export the snapshot and refresh Evidence sources
	$(PYTHON) scripts/check_dashboard_data.py
	$(MAKE) dashboard-snapshot
	cd dashboard && npm run sources:strict

dashboard-check: ## Validate the current snapshot, Evidence build and dependent filters
	$(PYTHON) scripts/check_dashboard_snapshot.py data/dashboard/latest.duckdb
	$(MAKE) race-control-audit
	cd dashboard && npm run sources:strict && npm run build:strict && npm run test:dropdown
	$(PYTHON) scripts/check_dashboard_bundle.py dashboard/build --max-total-mb 275

race-control-audit: ## Reconcile every published 2024-2026 race with source control messages
	$(PYTHON) scripts/audit_race_control_coverage.py data/dashboard/latest.duckdb --summary-only

data-audit: ## Audit snapshot provenance, checksum, coverage and freshness
	$(PYTHON) scripts/data_audit.py --strict

dashboard-dev: dashboard-prepare ## Prepare data and launch Evidence with the replay app
	cd dashboard && npm run dev

dagster: ## Launch the Dagster UI (asset graph + schedules)
	$(DAGSTER) dev -m orchestration.definitions

dagster-validate: ## Validate the Dagster definitions load
	$(DAGSTER) definitions validate -m orchestration.definitions

pg-up: ## Start the postgres container
	docker compose up -d postgres

pg-down: ## Stop compose services
	docker compose down

prod-up: ## Start persistent Postgres and Dagster services
	test -f .env.production || (echo "Copy .env.production.example to .env.production first" && exit 1)
	mkdir -p data/backups
	docker compose --env-file .env.production up -d --build

prod-down: ## Stop the persistent services without deleting volumes
	docker compose --env-file .env.production down

prod-logs: ## Follow Dagster and Postgres logs
	docker compose --env-file .env.production logs --follow postgres dagster-webserver dagster-daemon

prod-smoke: ## Check the persistent stack and Dagster definitions
	docker compose --env-file .env.production ps
	docker compose --env-file .env.production exec dagster-webserver dagster definitions validate -m orchestration.definitions
	docker compose --env-file .env.production exec dagster-webserver f1-ingest health

prod-backup: ## Back up the Postgres warehouse and Dagster history
	mkdir -p data/backups
	docker compose --env-file .env.production exec -T --user "$$(id -u):$$(id -g)" dagster-webserver f1-ingest backup-postgres --directory /app/data/backups

prod-restore-drill: ## Verify BACKUP in an isolated temporary database
	test -n "$(BACKUP)" || (echo "Usage: make prod-restore-drill BACKUP=data/backups/f1-...dump" && exit 1)
	docker compose --env-file .env.production exec -T --user "$$(id -u):$$(id -g)" dagster-webserver f1-ingest restore-drill --backup /app/$(BACKUP)

prod-restore-drill-latest: ## Verify the newest backup in an isolated database
	docker compose --env-file .env.production exec -T --user "$$(id -u):$$(id -g)" dagster-webserver f1-ingest restore-drill-latest --directory /app/data/backups

check: lint typecheck test ## Run lint, typecheck and tests
