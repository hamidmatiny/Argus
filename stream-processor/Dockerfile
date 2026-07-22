# syntax=docker/dockerfile:1
# ARGUS stream-processor — local QA engine (+ Flink client libs optional)

FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY stream-processor/requirements.txt /build/requirements.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r /build/requirements.txt

FROM python:3.12-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="argus-stream-processor" \
      org.opencontainers.image.description="ARGUS Flink/local telemetry QA gate"

RUN apt-get update && apt-get install -y --no-install-recommends \
    tini curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 argus \
    && useradd --uid 10001 --gid argus --create-home --shell /usr/sbin/nologin argus

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=argus:argus stream-processor/ /app/stream-processor/
COPY --chown=argus:argus ingestion/simulator/avro_codec.py /app/ingestion/simulator/avro_codec.py
COPY --chown=argus:argus ingestion/simulator/__init__.py /app/ingestion/simulator/__init__.py
COPY --chown=argus:argus ingestion/__init__.py /app/ingestion/__init__.py
COPY --chown=argus:argus shared/avro/ /app/shared/avro/

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/stream-processor:/app \
    ARGUS_AVRO_SCHEMA_PATH=/app/shared/avro/telemetry_event.avsc \
    QA_ENGINE=local \
    QA_HEALTH_PORT=8093

EXPOSE 8093
USER argus

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD curl -fsS http://127.0.0.1:8093/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "/app/stream-processor/main.py", "--engine", "local"]
