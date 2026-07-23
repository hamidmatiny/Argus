"""FastAPI app — POST /copilot/ask + health."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agent.agent import CopilotAgent
from agent.config import load_settings
from agent.llm import LLMClient
from agent.tools import ToolBelt
from ingestion.embed import Embedder

logger = logging.getLogger("argus.copilot")


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)


class AskResponse(BaseModel):
    answer: str
    tool_calls: list[dict[str, Any]]
    citations: list[str]
    rejected: bool = False
    reject_reason: str = ""


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    embedder = Embedder(settings)
    tools = ToolBelt(settings, embedder)
    llm = LLMClient(settings)
    app.state.settings = settings
    app.state.agent = CopilotAgent(settings, tools, llm)
    app.state.tools = tools
    logger.info(
        "copilot_ready provider=%s model=%s ready=%s",
        settings.llm_provider,
        settings.llm_model,
        settings.ready,
    )
    yield
    tools.close()


app = FastAPI(title="ARGUS AI Copilot", version="0.1.0", lifespan=lifespan)


@app.get("/health")
@app.get("/healthz")
def health() -> dict[str, Any]:
    settings = app.state.settings
    if not settings.ready:
        return {
            "status": "config_error",
            "reason": settings.ready_reason,
            "service": "ai-copilot",
            "ready": False,
        }
    return {"status": "ok", "service": "ai-copilot", "ready": True}


@app.get("/readyz")
def readyz() -> dict[str, Any]:
    body = health()
    if not body.get("ready"):
        raise HTTPException(status_code=503, detail=body)
    return body


@app.post("/copilot/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    result = app.state.agent.ask(req.question)
    if result.rejected:
        raise HTTPException(
            status_code=400,
            detail={"error": "rejected", "reason": result.reject_reason},
        )
    return AskResponse(
        answer=result.answer,
        tool_calls=result.tool_calls,
        citations=sorted(set(result.citations)),
        rejected=False,
    )


def main() -> None:
    import uvicorn

    settings = load_settings()
    host, _, port_s = settings.addr.partition(":")
    host = host or "0.0.0.0"
    port = int(port_s or "8090")
    uvicorn.run("agent.app:app", host=host if host != ":" else "0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()
