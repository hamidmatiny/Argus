"""Tool-calling agent loop with depth cap + guardrails."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from agent.config import Settings
from agent.guardrails import sanitize_user_question, validate_tool_name
from agent.llm import SYSTEM_PROMPT, LLMClient
from agent.tools import ToolBelt


@dataclass
class AskResult:
    answer: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    rejected: bool = False
    reject_reason: str = ""


class CopilotAgent:
    def __init__(self, settings: Settings, tools: ToolBelt, llm: LLMClient) -> None:
        self.settings = settings
        self.tools = tools
        self.llm = llm

    def ask(self, question: str) -> AskResult:
        guard = sanitize_user_question(question)
        if not guard.ok:
            return AskResult(
                answer="",
                rejected=True,
                reject_reason=guard.reason,
            )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": guard.sanitized},
        ]
        recorded: list[dict[str, Any]] = []
        citations: list[str] = []
        specs = self.tools.specs()

        for _depth in range(self.settings.max_tool_depth):
            resp = self.llm.complete(messages, specs)
            if not resp.tool_calls:
                return AskResult(
                    answer=(resp.content or "").strip()
                    or "I could not produce an answer from available tools.",
                    tool_calls=recorded,
                    citations=citations,
                )

            # Assistant message with tool calls (OpenAI shape for history)
            messages.append(
                {
                    "role": "assistant",
                    "content": resp.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in resp.tool_calls
                    ],
                }
            )

            for tc in resp.tool_calls:
                name_check = validate_tool_name(tc.name)
                if not name_check.ok:
                    result = {"error": name_check.reason}
                else:
                    result = self.tools.dispatch(tc.name, tc.arguments)
                recorded.append(
                    {"tool": tc.name, "arguments": tc.arguments, "result_preview": _preview(result)}
                )
                citations.extend(_citations_from(tc.name, result))
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result)[:8000],
                    }
                )

        return AskResult(
            answer="Stopped: tool-call depth limit reached. Partial findings may be incomplete.",
            tool_calls=recorded,
            citations=citations,
        )


def _preview(result: dict[str, Any]) -> str:
    return json.dumps(result)[:500]


def _citations_from(tool: str, result: dict[str, Any]) -> list[str]:
    cites: list[str] = []
    if tool == "search_runbooks":
        for h in result.get("hits") or []:
            meta = h.get("metadata") or {}
            if meta.get("source"):
                cites.append(f"runbook:{meta['source']}")
    if tool == "search_similar_incidents":
        for h in result.get("hits") or []:
            meta = h.get("metadata") or {}
            if meta.get("incident_id"):
                cites.append(f"incident:{meta['incident_id']}")
    if tool == "query_incidents":
        for inc in result.get("incidents") or []:
            if inc.get("incident_id"):
                cites.append(f"incident:{inc['incident_id']}")
    return cites
