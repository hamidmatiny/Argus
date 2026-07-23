"""Chunk markdown runbooks and incident JSON for embedding."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Chunk:
    chunk_id: str
    text: str
    metadata: dict


def chunk_markdown(path: Path, *, max_chars: int = 1200) -> list[Chunk]:
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"\n(?=## )", text)
    chunks: list[Chunk] = []
    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue
        if len(part) <= max_chars:
            blocks = [part]
        else:
            blocks = [
                part[j : j + max_chars] for j in range(0, len(part), max_chars)
            ]
        for k, block in enumerate(blocks):
            cid = f"{path.stem}-{i}-{k}"
            chunks.append(
                Chunk(
                    chunk_id=cid,
                    text=block,
                    metadata={
                        "source": str(path.name),
                        "kind": "runbook",
                        "title": path.stem.replace("-", " "),
                    },
                )
            )
    return chunks


def chunk_incident(record: dict, idx: int) -> Chunk:
    text = json.dumps(record, sort_keys=True, default=str)
    return Chunk(
        chunk_id=f"inc-{record.get('incident_id', idx)}",
        text=text,
        metadata={
            "kind": "incident",
            "incident_id": str(record.get("incident_id", "")),
            "vehicle_id": str(record.get("vehicle_id", "")),
            "severity": str(record.get("severity", "")),
            "reason": str(record.get("reason") or record.get("summary") or ""),
        },
    )


def load_incident_fixtures(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    return data.get("incidents") or []
