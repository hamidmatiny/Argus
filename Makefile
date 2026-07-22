# ARGUS — root developer targets
# Phase 0: scaffolding only. Per-language runners expand in later phases.

.PHONY: up down test lint proto logs help

COMPOSE ?= docker compose

help: ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?##"}; {printf "  %-12s %s\n", $$1, $$2}'

up: ## Start local stack (docker compose up -d --build)
	$(COMPOSE) up -d --build

down: ## Stop local stack
	$(COMPOSE) down

logs: ## Follow compose logs
	$(COMPOSE) logs -f

test: ## Fan-out tests (placeholders until components land)
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
	@echo "==> test: Python (pytest when packages exist)"
	@echo "  skip Python (no packages yet)"
	@echo "==> test: TypeScript (when packages exist)"
	@echo "  skip TypeScript (no packages yet)"
	@echo "==> test: e2e"
	@echo "  skip e2e (tests/e2e not populated yet)"

lint: ## Fan-out linters (placeholders until components land)
	@echo "==> lint: Go (golangci-lint when configured)"
	@echo "  skip Go lint (no sources yet)"
	@echo "==> lint: Python (ruff + mypy + black when packages exist)"
	@echo "  skip Python lint (no packages yet)"
	@echo "==> lint: TypeScript (eslint + prettier when packages exist)"
	@echo "  skip TypeScript lint (no packages yet)"

proto: ## Generate stubs from shared contracts (Phase 1+)
	@echo "proto: placeholder — Phase 1 will generate from shared/ schemas"
	@exit 0
