"""ai-copilot configuration — all secrets from environment (fail-fast)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _req(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        raise RuntimeError(f"{name} is required")
    return v


@dataclass(frozen=True)
class Settings:
    addr: str
    llm_provider: str  # openai | anthropic | mock
    llm_api_key: str | None
    llm_api_base: str | None
    llm_model: str
    embedding_provider: str  # openai | hash
    embedding_model: str
    qdrant_url: str
    collection_runbooks: str
    collection_incidents: str
    incident_engine_url: str
    drift_monitor_url: str
    gateway_url: str
    gateway_api_key: str
    drift_reports_dir: Path
    runbooks_dir: Path
    fixtures_dir: Path
    max_tool_depth: int
    ready_reason: str | None = None

    @property
    def ready(self) -> bool:
        return self.ready_reason is None


def load_settings() -> Settings:
    """Load settings. LLM key required unless LLM_PROVIDER=mock (eval/CI)."""
    provider = os.environ.get("LLM_PROVIDER", "openai").strip().lower()
    ready_reason: str | None = None
    api_key: str | None = None

    if provider == "mock":
        api_key = None
    elif provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("LLM_API_KEY")
        if not api_key:
            ready_reason = "ANTHROPIC_API_KEY (or LLM_API_KEY) missing"
    else:
        # openai-compatible (OpenAI, Groq, xAI, local vLLM, etc.)
        api_key = (
            os.environ.get("LLM_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("GROQ_API_KEY")
            or os.environ.get("XAI_API_KEY")
        )
        if not api_key:
            ready_reason = "LLM_API_KEY / OPENAI_API_KEY missing"

    root = Path(__file__).resolve().parents[1]
    return Settings(
        addr=os.environ.get("COPILOT_ADDR", ":8090"),
        llm_provider=provider,
        llm_api_key=api_key,
        llm_api_base=os.environ.get("LLM_API_BASE_URL") or os.environ.get("OPENAI_API_BASE"),
        llm_model=os.environ.get("LLM_MODEL", "gpt-4o-mini"),
        embedding_provider=os.environ.get("EMBEDDING_PROVIDER", "hash").lower(),
        embedding_model=os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small"),
        qdrant_url=os.environ.get("QDRANT_URL", "http://localhost:6333"),
        collection_runbooks=os.environ.get("QDRANT_COLLECTION_RUNBOOKS", "argus_runbooks"),
        collection_incidents=os.environ.get("QDRANT_COLLECTION_INCIDENTS", "argus_incidents"),
        incident_engine_url=os.environ.get(
            "INCIDENT_ENGINE_URL", "http://localhost:8098"
        ).rstrip("/"),
        drift_monitor_url=os.environ.get(
            "DRIFT_MONITOR_URL", "http://localhost:8094"
        ).rstrip("/"),
        gateway_url=os.environ.get("ARGUS_GATEWAY_URL", "http://localhost:8099").rstrip(
            "/"
        ),
        gateway_api_key=os.environ.get("ARGUS_API_KEY", "demo-viewer"),
        drift_reports_dir=Path(
            os.environ.get("DRIFT_REPORTS_DIR", str(root.parent / "drift-monitor" / "reports"))
        ),
        runbooks_dir=Path(os.environ.get("COPILOT_RUNBOOKS_DIR", str(root / "runbooks"))),
        fixtures_dir=Path(os.environ.get("COPILOT_FIXTURES_DIR", str(root / "fixtures"))),
        max_tool_depth=int(os.environ.get("COPILOT_MAX_TOOL_DEPTH", "6")),
        ready_reason=ready_reason,
    )
