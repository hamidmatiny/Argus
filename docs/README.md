# docs

MkDocs Material documentation for ARGUS (portfolio + operator facing).

## Build locally

```bash
pip install -r docs/requirements.txt
# from repo root:
mkdocs serve
mkdocs build --strict
```

## Contents

| Path | Purpose |
|------|---------|
| `getting-started.md` | First 5 minutes |
| `architecture.md` | System diagrams (Mermaid) |
| `components/` | Per-component index → repo READMEs |
| `adr/` | Architecture Decision Records |
| `operations-runbook.md` | Human ops (mirrors ai-copilot runbooks) |
| `DEMO_SCRIPT.md` | Literal 5-minute demo |
| `CASE_STUDY.md` | Portfolio write-up |
| `assets/screenshots/` | Drop demo PNGs/GIFs here |

Config: [`mkdocs.yml`](../mkdocs.yml) at repo root.
