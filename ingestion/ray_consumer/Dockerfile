# syntax=docker/dockerfile:1
# ARGUS Ray telemetry consumer — multi-stage, non-root

FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY ingestion/requirements.txt /build/requirements.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r /build/requirements.txt

FROM python:3.12-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="argus-ingestion-ray-consumer" \
      org.opencontainers.image.description="ARGUS Ray Core telemetry ingestion"

RUN apt-get update && apt-get install -y --no-install-recommends \
    tini \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 argus \
    && useradd --uid 10001 --gid argus --create-home --shell /usr/sbin/nologin argus

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=argus:argus ingestion/ /app/ingestion/
COPY --chown=argus:argus shared/avro/ /app/shared/avro/

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    ARGUS_AVRO_SCHEMA_PATH=/app/shared/avro/telemetry_event.avsc \
    RAY_HEALTH_PORT=8092 \
    RAY_DASHBOARD_HOST=0.0.0.0 \
    RAY_DASHBOARD_PORT=8265 \
    RAY_OBJECT_STORE_MEMORY_BYTES=268435456 \
    RAY_MEMORY_BYTES=536870912 \
    RAY_INCLUDE_DASHBOARD=false \
    RAY_ACCEL_ENV_VAR_OVERRIDE_ON_ZERO=0

EXPOSE 8092 8265
USER argus

HEALTHCHECK --interval=20s --timeout=5s --start-period=45s --retries=5 \
  CMD curl -fsS http://127.0.0.1:8092/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "ingestion.ray_consumer"]
