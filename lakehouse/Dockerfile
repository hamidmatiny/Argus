# syntax=docker/dockerfile:1
# ARGUS lakehouse writers — Kafka → Iceberg (telemetry + quarantine)

FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY lakehouse/requirements.txt /build/requirements.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r /build/requirements.txt

FROM python:3.12-slim-bookworm AS runtime

ARG LAKEHOUSE_SERVICE=writer
LABEL org.opencontainers.image.title="argus-lakehouse" \
      org.opencontainers.image.description="ARGUS Iceberg lakehouse Kafka writers"

RUN apt-get update && apt-get install -y --no-install-recommends \
    tini curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 argus \
    && useradd --uid 10001 --gid argus --create-home --shell /usr/sbin/nologin argus

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=argus:argus lakehouse/ /app/lakehouse/
COPY --chown=argus:argus ingestion/simulator/avro_codec.py /app/ingestion/simulator/avro_codec.py
COPY --chown=argus:argus ingestion/simulator/__init__.py /app/ingestion/simulator/__init__.py
COPY --chown=argus:argus ingestion/__init__.py /app/ingestion/__init__.py
COPY --chown=argus:argus shared/avro/ /app/shared/avro/

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/lakehouse:/app \
    ARGUS_AVRO_SCHEMA_PATH=/app/shared/avro/telemetry_event.avsc \
    LAKEHOUSE_SERVICE=${LAKEHOUSE_SERVICE} \
    LAKEHOUSE_WRITER_HEALTH_PORT=8096 \
    LAKEHOUSE_DLQ_HEALTH_PORT=8097

EXPOSE 8096 8097
USER argus

# Compose overrides per-service healthchecks (8096 writer / 8097 dlq).
HEALTHCHECK --interval=20s --timeout=5s --start-period=45s --retries=5 \
  CMD curl -fsS http://127.0.0.1:8096/health || curl -fsS http://127.0.0.1:8097/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
# Override command per compose service.
CMD ["python", "/app/lakehouse/writer/main.py"]
