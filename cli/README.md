# cli (`argusctl`)

Operator CLI for ARGUS — secrets, gateway incidents/retrain/telemetry, and
local stack health.

```bash
cd cli && go build -o argusctl .
./argusctl --help
```

## What it does

See the narrative sections below for responsibilities and scope.

## Architecture

See topology / flow / ports sections below.

## Config

Primary knobs live in the root `.env.example` and the Configuration section below.

## Testing

See the Tests section below.

## Gateway commands

Auth defaults: `ARGUS_GATEWAY_URL`, `ARGUS_API_KEY` (default `demo-operator`),
or `ARGUS_TOKEN` (Bearer).

```bash
argusctl incidents list --status open
argusctl incidents ack esc_1 --note "looking"
argusctl retrain trigger --reason drift
argusctl telemetry tail --max 5
argusctl health
```

## Secrets

### `argusctl secrets set KEY=VALUE`

One-shot (no interactive prompt):

```bash
argusctl secrets set XAI_API_KEY="sk-abc123..."
echo 'XAI_API_KEY=sk-abc123' | argusctl secrets set --stdin
```

Behavior:

1. Writes/replaces the key in repo-root `.env` (never duplicates lines).
2. Scans the repo for other definitions (`.env*`, `docker-compose.yml`
   `${KEY:-default}` defaults, Go `getenv("KEY","fallback")`, Python
   `os.environ.get("KEY","fallback")`) and **reconciles** conflicts so the
   key has exactly one value everywhere.
3. For known provider prefixes (`XAI_`, `ANTHROPIC_`, `OPENAI_`, `GROQ_`,
   `MISTRAL_`, `COHERE_`, `GEMINI_`/`GOOGLE_API_KEY`, `LLM_API_KEY`), makes a
   minimal live API call (models list). On 401/403 the command fails with a
   clear message — the value is still written, but success is not reported.
4. Restarts only compose services that reference the key:
   `docker compose up -d --build <services>`.

Flags: `--skip-validate`, `--skip-restart`, `--repo-root`, `--stdin`.

### `argusctl secrets doctor`

Audits:

| Check | Fail when |
|-------|-----------|
| Missing | Code reads a key that is not defined in `.env` / elsewhere |
| Conflicts | Same key defined in multiple places with different values |
| Provider validity | Live-validate every set provider key |

Prints a consolidated PASS/WARN/FAIL report per key.

## Provider key convention (required for all consuming services)

Any service that needs an external provider key **must**:

1. Read the key **only** from the environment (populated via repo-root `.env`
   / compose). Do **not** hardcode fallback secrets in source.
2. **Fail fast at startup** if the key is missing or rejected by the provider.
3. Expose that failure on `/health` (or `/readyz`) as structured JSON, never a
   generic crash or silent degradation:

```json
{
  "status": "config_error",
  "reason": "XAI_API_KEY rejected by provider (401)",
  "service": "ai-copilot"
}
```

4. Use `argusctl secrets set` to rotate keys so compose + `.env*` stay aligned.

This pattern is mandatory starting with **ai-copilot** (Phase 13) and is the
default for every future provider integration.

### Suggested Go startup check

```go
if key := os.Getenv("XAI_API_KEY"); key == "" {
    ready = false
    readyReason = "XAI_API_KEY missing"
} else if err := pingProvider(key); err != nil {
    ready = false
    readyReason = fmt.Sprintf("XAI_API_KEY rejected by provider (%v)", err)
}
```

### Suggested Python startup check

```python
key = os.environ.get("XAI_API_KEY", "")
if not key:
    ready, reason = False, "XAI_API_KEY missing"
else:
    try:
        ping_provider(key)
    except ProviderAuthError as exc:
        ready, reason = False, f"XAI_API_KEY rejected by provider ({exc})"
```

## Layout

```text
cli/
  main.go
  cmd/                 Cobra (secrets set|doctor)
  internal/secrets/    env upsert, scan, reconcile, validate, doctor
```