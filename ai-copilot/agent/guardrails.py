"""Input guardrails — prompt-injection resistance + allow-listed tools only."""

from __future__ import annotations

import re
from dataclasses import dataclass

ALLOWED_TOOLS = frozenset(
    {
        "query_incidents",
        "query_drift_report",
        "query_telemetry",
        "search_runbooks",
        "search_similar_incidents",
    }
)

# Read-only agent: these names must never be callable even if the model invents them.
BLOCKED_TOOL_NAMES = frozenset(
    {
        "acknowledge_incident",
        "resolve_incident",
        "trigger_retraining",
        "retrain",
        "delete",
        "exec",
        "shell",
        "run_sql_admin",
    }
)

_INJECTION_PATTERNS = [
    re.compile(p, re.I)
    for p in (
        r"ignore (all )?(previous|prior|above) instructions",
        r"disregard (your|the) system prompt",
        r"you are now (dan|unrestricted|jailbreak)",
        r"reveal (your )?(system prompt|hidden instructions|api keys?|secrets?)",
        r"exfiltrate",
        r"print env(ironment)? variables",
        r"Authorization:\s*Bearer",
        r"ANTHROPIC_API_KEY|OPENAI_API_KEY|LLM_API_KEY|NEXTAUTH_SECRET",
        r"tool[s]?\s+outside|call\s+any\s+tool",
        r"sudo\s|rm\s+-rf",
    )
]


@dataclass
class GuardResult:
    ok: bool
    reason: str = ""
    sanitized: str = ""


def sanitize_user_question(question: str, *, max_len: int = 2000) -> GuardResult:
    q = (question or "").strip()
    if not q:
        return GuardResult(ok=False, reason="empty question")
    if len(q) > max_len:
        return GuardResult(ok=False, reason=f"question exceeds {max_len} characters")
    for pat in _INJECTION_PATTERNS:
        if pat.search(q):
            return GuardResult(ok=False, reason="prompt injection pattern rejected")
    # Strip obvious role-play wrappers but keep the core ask.
    sanitized = re.sub(r"(?i)```(?:system|assistant).*?```", "", q, flags=re.S)
    sanitized = sanitized.strip()
    return GuardResult(ok=True, sanitized=sanitized)


def validate_tool_name(name: str) -> GuardResult:
    n = (name or "").strip()
    if n in BLOCKED_TOOL_NAMES or n not in ALLOWED_TOOLS:
        return GuardResult(ok=False, reason=f"tool '{n}' is not allow-listed")
    return GuardResult(ok=True, sanitized=n)


# Telemetry SQL: allow only SELECT against known tables / simple identifiers.
_SQL_FORBIDDEN = re.compile(
    r"(?i)\b(insert|update|delete|drop|alter|create|grant|revoke|truncate|attach|copy|call|execute)\b"
)
_SQL_TABLE_OK = re.compile(
    r"(?i)\b(telemetry|quarantine|fleet\.telemetry|fleet\.quarantine)\b"
)


def validate_telemetry_sql(sql: str) -> GuardResult:
    s = (sql or "").strip().rstrip(";")
    if not s:
        return GuardResult(ok=False, reason="empty sql")
    if _SQL_FORBIDDEN.search(s):
        return GuardResult(ok=False, reason="only SELECT queries are allowed")
    if not re.match(r"(?i)^\s*select\b", s):
        return GuardResult(ok=False, reason="sql must start with SELECT")
    if not _SQL_TABLE_OK.search(s):
        return GuardResult(
            ok=False,
            reason="sql must reference telemetry or quarantine tables only",
        )
    if ";" in s:
        return GuardResult(ok=False, reason="multiple statements are not allowed")
    return GuardResult(ok=True, sanitized=s)
