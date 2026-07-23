"""Index runbooks + historical incidents into Qdrant."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

# Allow `python -m ingestion.index` from ai-copilot/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.config import load_settings  # noqa: E402
from ingestion.chunk import chunk_incident, chunk_markdown, load_incident_fixtures  # noqa: E402
from ingestion.embed import Embedder  # noqa: E402

logger = logging.getLogger("argus.copilot.ingestion")


def ensure_collection(client: QdrantClient, name: str, dim: int) -> None:
    names = {c.name for c in client.get_collections().collections}
    if name in names:
        return
    client.create_collection(
        collection_name=name,
        vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
    )


def upsert_chunks(
    client: QdrantClient,
    collection: str,
    embedder: Embedder,
    chunks: list,
) -> int:
    if not chunks:
        return 0
    vectors = embedder.embed([c.text for c in chunks])
    ensure_collection(client, collection, len(vectors[0]))
    points = []
    for chunk, vec in zip(chunks, vectors, strict=True):
        points.append(
            qm.PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, chunk.chunk_id)),
                vector=vec,
                payload={"text": chunk.text, **chunk.metadata},
            )
        )
    client.upsert(collection_name=collection, points=points)
    return len(points)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Embed ARGUS runbooks + incidents into Qdrant")
    parser.add_argument("--recreate", action="store_true")
    args = parser.parse_args()

    settings = load_settings()
    embedder = Embedder(settings)
    client = QdrantClient(url=settings.qdrant_url, check_compatibility=False)

    if args.recreate:
        for name in (settings.collection_runbooks, settings.collection_incidents):
            try:
                client.delete_collection(name)
            except Exception:
                pass

    runbook_chunks = []
    for path in sorted(settings.runbooks_dir.glob("*.md")):
        runbook_chunks.extend(chunk_markdown(path))
    n_rb = upsert_chunks(client, settings.collection_runbooks, embedder, runbook_chunks)
    logger.info("indexed_runbooks count=%s", n_rb)

    incidents = load_incident_fixtures(settings.fixtures_dir / "historical_incidents.json")
    # Optional live pull from incident-engine
    try:
        import httpx

        with httpx.Client(timeout=5.0) as http:
            res = http.get(f"{settings.incident_engine_url}/incidents")
            if res.is_success:
                live = res.json().get("incidents") or []
                incidents.extend(live)
    except Exception as exc:  # noqa: BLE001
        logger.info("live_incidents_skip err=%s", exc)

    inc_chunks = [chunk_incident(rec, i) for i, rec in enumerate(incidents)]
    n_inc = upsert_chunks(client, settings.collection_incidents, embedder, inc_chunks)
    logger.info("indexed_incidents count=%s", n_inc)
    print(json.dumps({"runbooks": n_rb, "incidents": n_inc}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
