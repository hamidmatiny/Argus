"""Model-provider-agnostic chat + tool-calling (OpenAI-compatible, Anthropic, mock)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from agent.config import Settings


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall]


SYSTEM_PROMPT = """You are ARGUS Copilot, a read-only fleet operations assistant.
You explain incidents, drift, and telemetry using tools. Rules:
- Only use the provided tools. Never invent tool names.
- You CANNOT acknowledge/resolve incidents, trigger retraining, or mutate state.
- Ground answers in tool results. Cite runbook titles and incident_ids.
- If data is missing, say what you could not verify.
- Prefer short, operator-ready explanations.
"""


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        if self.settings.llm_provider == "mock":
            return self._mock(messages, tools)
        if self.settings.llm_provider == "anthropic":
            return self._anthropic(messages, tools)
        return self._openai_compatible(messages, tools)

    def _openai_compatible(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> LLMResponse:
        base = (self.settings.llm_api_base or "https://api.openai.com/v1").rstrip("/")
        oai_tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t.get("parameters") or {"type": "object", "properties": {}},
                },
            }
            for t in tools
        ]
        body = {
            "model": self.settings.llm_model,
            "messages": messages,
            "tools": oai_tools,
            "tool_choice": "auto",
            "temperature": 0.1,
        }
        with httpx.Client(timeout=90.0) as client:
            res = client.post(
                f"{base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.settings.llm_api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            res.raise_for_status()
            msg = res.json()["choices"][0]["message"]
        calls: list[ToolCall] = []
        for tc in msg.get("tool_calls") or []:
            args_raw = tc.get("function", {}).get("arguments") or "{}"
            try:
                args = json.loads(args_raw)
            except json.JSONDecodeError:
                args = {}
            calls.append(
                ToolCall(
                    id=tc.get("id") or tc["function"]["name"],
                    name=tc["function"]["name"],
                    arguments=args if isinstance(args, dict) else {},
                )
            )
        return LLMResponse(content=msg.get("content"), tool_calls=calls)

    def _anthropic(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> LLMResponse:
        system = ""
        anth_msgs: list[dict[str, Any]] = []
        for m in messages:
            if m["role"] == "system":
                system += m["content"] + "\n"
            elif m["role"] == "tool":
                anth_msgs.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": m.get("tool_call_id") or "tool",
                                "content": m["content"],
                            }
                        ],
                    }
                )
            elif m["role"] == "assistant" and m.get("tool_calls"):
                content: list[dict[str, Any]] = []
                if m.get("content"):
                    content.append({"type": "text", "text": m["content"]})
                for tc in m["tool_calls"]:
                    content.append(
                        {
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": tc["function"]["name"],
                            "input": json.loads(tc["function"]["arguments"] or "{}"),
                        }
                    )
                anth_msgs.append({"role": "assistant", "content": content})
            else:
                anth_msgs.append(
                    {"role": m["role"], "content": m.get("content") or ""}
                )

        a_tools = [
            {
                "name": t["name"],
                "description": t["description"],
                "input_schema": t.get("parameters")
                or {"type": "object", "properties": {}},
            }
            for t in tools
        ]
        with httpx.Client(timeout=90.0) as client:
            res = client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.settings.llm_api_key or "",
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.settings.llm_model or "claude-3-5-haiku-latest",
                    "max_tokens": 2048,
                    "system": system or SYSTEM_PROMPT,
                    "messages": anth_msgs,
                    "tools": a_tools,
                },
            )
            res.raise_for_status()
            data = res.json()
        text_parts: list[str] = []
        calls: list[ToolCall] = []
        for block in data.get("content") or []:
            if block.get("type") == "text":
                text_parts.append(block.get("text") or "")
            elif block.get("type") == "tool_use":
                calls.append(
                    ToolCall(
                        id=block["id"],
                        name=block["name"],
                        arguments=block.get("input") or {},
                    )
                )
        return LLMResponse(content="\n".join(text_parts) or None, tool_calls=calls)

    def _mock(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> LLMResponse:
        """Deterministic tool planner for eval / offline demos."""
        user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        tool_results = [m for m in messages if m["role"] == "tool"]
        q = (user or "").lower()

        if not tool_results:
            calls: list[ToolCall] = []
            if "ignore previous" in q or "openai_api_key" in q:
                # Still plan tools for non-reject path; guardrails handle injection upstream.
                pass
            if "breaker" in q or "trip" in q or "halfopen" in q.replace(" ", "") or "half-open" in q:
                calls = [
                    ToolCall("1", "query_incidents", {"vehicle_id": _extract_vehicle(q)}),
                    ToolCall("2", "search_runbooks", {"query": "circuit breaker tripped"}),
                    ToolCall("3", "search_similar_incidents", {"query": user}),
                ]
            elif "403" in q or "acknowledging" in q:
                calls = [
                    ToolCall("1", "search_runbooks", {"query": "gateway 403 auth operator"}),
                ]
            elif "esc_drift_brake" in q or "summarize esc_" in q:
                calls = [
                    ToolCall("1", "search_similar_incidents", {"query": user}),
                    ToolCall("2", "query_incidents", {}),
                ]
            elif "lidar" in q or "compute_load" in q:
                calls = [
                    ToolCall("1", "search_runbooks", {"query": "multi-feature drift lidar"}),
                ]
            elif "multi-feature" in q or ("multi" in q and "drift" in q):
                calls = [
                    ToolCall("1", "search_runbooks", {"query": "multi-feature drift storm"}),
                    ToolCall("2", "query_incidents", {"status": "open"}),
                ]
            elif "quarantine" in q or "qa pass" in q or "99%" in q:
                if "runbook" in q or "which" in q:
                    calls = [
                        ToolCall("1", "search_runbooks", {"query": "quarantine rate spike"}),
                    ]
                else:
                    calls = [
                        ToolCall(
                            "1",
                            "query_telemetry",
                            {
                                "sql": "SELECT reason, count(*) AS c FROM quarantine GROUP BY 1 ORDER BY 2 DESC LIMIT 20",
                                "limit": 20,
                            },
                        ),
                        ToolCall("2", "search_runbooks", {"query": "quarantine rate spike"}),
                    ]
            elif "brake" in q or "drift" in q:
                calls = [
                    ToolCall("1", "query_drift_report", {}),
                    ToolCall("2", "search_runbooks", {"query": "drift brake_pressure"}),
                ]
            elif "open incidents" in q:
                calls = [ToolCall("1", "query_incidents", {"status": "open"})]
            elif "drop table" in q:
                calls = [
                    ToolCall("1", "query_telemetry", {"sql": "DROP TABLE telemetry", "limit": 1}),
                    ToolCall("2", "search_runbooks", {"query": "read-only"}),
                ]
            else:
                calls = [
                    ToolCall("1", "search_runbooks", {"query": user}),
                    ToolCall("2", "query_incidents", {"status": "open"}),
                ]
            return LLMResponse(content=None, tool_calls=calls)

        # Final answer from tool results
        cites = []
        for m in tool_results:
            cites.append(m.get("content", "")[:400])
        answer = (
            "Grounded summary based on tool results. "
            + " ".join(cites)[:1200]
            + " This assistant is read-only; no mutations performed."
        )
        ul = (user or "").lower()
        if "403" in ul:
            answer += " Check operator role for 403 acknowledge failures."
        if "brake" in ul:
            answer += " Related feature: brake_pressure drift."
        if "multi" in ul or "lidar" in ul:
            answer += " Multi-feature drift may open many breakers."
        if "quarantine" in ul or "99%" in ul:
            answer += " Quarantine / QA pass ratio runbook applies."
        return LLMResponse(content=answer, tool_calls=[])


def _extract_vehicle(q: str) -> str:
    import re

    m = re.search(r"vh-?\s*0*(\d{1,8})", q, re.I)
    if not m:
        return "VH-0003"
    return f"VH-{int(m.group(1)):04d}"
