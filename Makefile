# ARGUS — root developer targets

.PHONY: up down test lint proto contracts-test ingestion-test stream-processor-test drift-monitor-test lakehouse-test orchestration-test incident-engine-test api-gateway-test cli-test register-avro logs help

COMPOSE ?= docker compose
BUF ?= buf
# Prefer 3.12 when present (wheels for numpy/scipy/evidently); fall back to python3.
PYTHON ?= $(shell command -v python3.12 >/dev/null 2>&1 && echo python3.12 || echo python3)
CONTRACTS_DIR := shared/contracts
CONTRACTS_VENV := $(CONTRACTS_DIR)/.venv
CONTRACTS_PIP := $(CONTRACTS_VENV)/bin/pip
INGESTION_DIR := ingestion
INGESTION_VENV := $(INGESTION_DIR)/.venv
INGESTION_PIP := $(INGESTION_VENV)/bin/pip
STREAM_DIR := stream-processor
STREAM_VENV := $(STREAM_DIR)/.venv
STREAM_PIP := $(STREAM_VENV)/bin/pip
DRIFT_DIR := drift-monitor
DRIFT_VENV := $(DRIFT_DIR)/.venv
DRIFT_PIP := $(DRIFT_VENV)/bin/pip
LAKE_DIR := lakehouse
LAKE_VENV := $(LAKE_DIR)/.venv
LAKE_PIP := $(LAKE_VENV)/bin/pip
ORCH_DIR := orchestration
ORCH_VENV := $(ORCH_DIR)/.venv
ORCH_PIP := $(ORCH_VENV)/bin/pip

help: ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?##"}; {printf "  %-22s %s\n", $$1, $$2}'

up: ## Start local stack (docker compose up -d --build)
	$(COMPOSE) up -d --build

down: ## Stop local stack
	$(COMPOSE) down

logs: ## Follow compose logs
	$(COMPOSE) logs -f

test: contracts-test ingestion-test stream-processor-test drift-monitor-test lakehouse-test orchestration-test incident-engine-test api-gateway-test cli-test ## Fan-out tests
	@echo "==> test: Go modules (go.work)"
	@if command -v go >/dev/null 2>&1; then \
		go work sync 2>/dev/null || true; \
		for m in api-gateway cli; do \
			if [ -d "$$m" ] && [ -f "$$m/go.mod" ]; then \
				(cd "$$m" && go test ./...) || true; \
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

proto: ## buf lint + buf generate (Go + Python stubs + OpenAPI)
	@command -v $(BUF) >/dev/null 2>&1 || { echo "error: buf not found — install https://buf.build"; exit 1; }
	cd shared/proto && $(BUF) dep update
	cd shared/proto && $(BUF) lint
	cd shared/proto && $(BUF) generate
	@mkdir -p shared/gen/python/argus/v1 api-gateway/openapi
	@touch shared/gen/python/argus/__init__.py shared/gen/python/argus/v1/__init__.py
	@cp -f shared/gen/openapi/argus/v1/gateway.swagger.json api-gateway/openapi/gateway.swagger.json
	@cd shared/gen/go && go mod tidy
	@echo "proto: generated shared/gen/{go,python,openapi} + api-gateway/openapi"

$(CONTRACTS_VENV)/bin/pytest: $(CONTRACTS_DIR)/pyproject.toml
	$(PYTHON) -m venv $(CONTRACTS_VENV)
	$(CONTRACTS_PIP) install -U pip
	$(CONTRACTS_PIP) install -e "$(CONTRACTS_DIR)[dev]"

contracts-test: proto $(CONTRACTS_VENV)/bin/pytest ## Schema drift guardrails
	cd $(CONTRACTS_DIR) && .venv/bin/pytest -q

$(INGESTION_VENV)/bin/pytest: $(INGESTION_DIR)/requirements.txt
	$(PYTHON) -m venv $(INGESTION_VENV)
	$(INGESTION_PIP) install -U pip
	$(INGESTION_PIP) install -r $(INGESTION_DIR)/requirements.txt

ingestion-test: $(INGESTION_VENV)/bin/pytest ## Simulator + Ray normalization tests
	cd $(INGESTION_DIR) && \
		PYTHONPATH=.. ARGUS_AVRO_SCHEMA_PATH=../shared/avro/telemetry_event.avsc \
		.venv/bin/pytest -q

$(STREAM_VENV)/bin/pytest: $(STREAM_DIR)/requirements.txt
	$(PYTHON) -m venv $(STREAM_VENV)
	$(STREAM_PIP) install -U pip
	$(STREAM_PIP) install -r $(STREAM_DIR)/requirements.txt

stream-processor-test: $(STREAM_VENV)/bin/pytest ## QA validation + local/Flink unit tests
	cd $(STREAM_DIR) && \
		PYTHONPATH=.:.. ARGUS_AVRO_SCHEMA_PATH=../shared/avro/telemetry_event.avsc \
		.venv/bin/pytest -q

$(DRIFT_VENV)/bin/pytest: $(DRIFT_DIR)/requirements.txt
	$(PYTHON) -m venv $(DRIFT_VENV)
	$(DRIFT_PIP) install -U pip
	$(DRIFT_PIP) install -r $(DRIFT_DIR)/requirements.txt

drift-monitor-test: $(DRIFT_VENV)/bin/pytest ## KS/Evidently drift + incident publishing tests
	cd $(DRIFT_DIR) && \
		PYTHONPATH=.:.. ARGUS_AVRO_SCHEMA_PATH=../shared/avro/telemetry_event.avsc \
		KAFKA_BROKERS=$${KAFKA_BROKERS:-localhost:19092} \
		.venv/bin/pytest -q

$(LAKE_VENV)/bin/pytest: $(LAKE_DIR)/requirements.txt
	$(PYTHON) -m venv $(LAKE_VENV)
	$(LAKE_PIP) install -U pip
	$(LAKE_PIP) install -r $(LAKE_DIR)/requirements.txt

lakehouse-test: $(LAKE_VENV)/bin/pytest ## Iceberg schema mapping + sqlite catalog appends
	cd $(LAKE_DIR) && \
		PYTHONPATH=.:.. \
		.venv/bin/pytest -q

$(ORCH_VENV)/bin/pytest: $(ORCH_DIR)/requirements.txt
	$(PYTHON) -m venv $(ORCH_VENV)
	$(ORCH_PIP) install -U pip
	$(ORCH_PIP) install -r $(ORCH_DIR)/requirements.txt

orchestration-test: $(ORCH_VENV)/bin/pytest ## Dagster assets + retrain decision logic
	cd $(ORCH_DIR) && \
		PYTHONPATH=.:.. \
		.venv/bin/pytest -q

incident-engine-test: ## Circuit breaker FSM + OPA/Rego policy unit tests
	cd incident-engine && go test ./...

api-gateway-test: ## Gateway middleware, OPA RBAC, mocked upstream integration
	cd api-gateway && go test ./...

cli-test: ## argusctl secrets set/doctor unit tests
	cd cli && go test ./...

register-avro: ## Register TelemetryEvent Avro schema with local Schema Registry
	bash shared/avro/register.sh
