# syntax=docker/dockerfile:1
# ARGUS fleet telemetry simulator — multi-stage, non-root

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

LABEL org.opencontainers.image.title="argus-ingestion-simulator" \
      org.opencontainers.image.description="ARGUS fleet telemetry simulator"

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
    SIMULATOR_HEALTH_PORT=8091

EXPOSE 8091
USER argus

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8091/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "ingestion.simulator"]
