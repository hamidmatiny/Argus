# ARGUS — root developer targets

.PHONY: up down test lint proto contracts-test register-avro logs help

COMPOSE ?= docker compose
BUF ?= buf
PYTHON ?= python3
CONTRACTS_DIR := shared/contracts
CONTRACTS_VENV := $(CONTRACTS_DIR)/.venv
CONTRACTS_PY := $(CONTRACTS_VENV)/bin/python
CONTRACTS_PIP := $(CONTRACTS_VENV)/bin/pip

help: ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?##"}; {printf "  %-16s %s\n", $$1, $$2}'

up: ## Start local stack (docker compose up -d --build)
	$(COMPOSE) up -d --build

down: ## Stop local stack
	$(COMPOSE) down

logs: ## Follow compose logs
	$(COMPOSE) logs -f

test: contracts-test ## Fan-out tests
	@echo "==> test: Go modules (go.work)"
	@if command -v go >/dev/null 2>&1; then \
		go work sync 2>/dev/null || true; \
		for m in incident-engine api-gateway cli; do \
			if [ -d "$$m" ] && ls "$$m"/*_test.go >/dev/null 2>&1; then \
				(cd "$$m" && go test ./...); \
			else \
				echo "  skip $$m (no tests yet)"; \
			fi; \
		done; \
	else \
		echo "  skip Go (go not installed)"; \
	fi
	@echo "==> test: TypeScript (when packages exist)"
	@echo "  skip TypeScript (no packages yet)"
	@echo "==> test: e2e"
	@echo "  skip e2e (tests/e2e not populated yet)"

lint: ## Fan-out linters
	@echo "==> lint: buf"
	@cd shared/proto && $(BUF) lint
	@echo "==> lint: Go (golangci-lint when configured)"
	@echo "  skip Go lint (no sources yet)"
	@echo "==> lint: Python (ruff + mypy + black when packages exist)"
	@echo "  skip Python lint (full suite not wired yet)"
	@echo "==> lint: TypeScript (eslint + prettier when packages exist)"
	@echo "  skip TypeScript lint (no packages yet)"

proto: ## buf lint + buf generate (Go + Python stubs)
	@command -v $(BUF) >/dev/null 2>&1 || { echo "error: buf not found — install https://buf.build"; exit 1; }
	cd shared/proto && $(BUF) lint
	cd shared/proto && $(BUF) generate
	@# Ensure Python packages are importable (buf may not emit __init__.py)
	@mkdir -p shared/gen/python/argus/v1
	@touch shared/gen/python/argus/__init__.py shared/gen/python/argus/v1/__init__.py
	@echo "proto: generated shared/gen/{go,python}"

$(CONTRACTS_VENV)/bin/pytest: $(CONTRACTS_DIR)/pyproject.toml
	$(PYTHON) -m venv $(CONTRACTS_VENV)
	$(CONTRACTS_PIP) install -U pip
	$(CONTRACTS_PIP) install -e "$(CONTRACTS_DIR)[dev]"

contracts-test: proto $(CONTRACTS_VENV)/bin/pytest ## Schema drift guardrails (Pydantic/Pandera/Avro/proto)
	cd $(CONTRACTS_DIR) && .venv/bin/pytest -q

register-avro: ## Register TelemetryEvent Avro schema with local Schema Registry
	bash shared/avro/register.sh
