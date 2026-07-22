# cli

Operator **CLI** for local diagnostics, incident inspection, pipeline status, and copilot queries against a running ARGUS stack.

**Status:** Scaffold only — implemented in a later phase.

**Language:** Go

**Responsibilities (planned):**
- `argus` binary with subcommands for status, incidents, and query
- Config via flags / env / config file
- Talks to api-gateway (not internal services directly)
