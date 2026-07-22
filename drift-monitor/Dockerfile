# syntax=docker/dockerfile:1
# ARGUS drift-monitor — KS + Evidently drift detection on telemetry.validated

FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY drift-monitor/requirements.txt /build/requirements.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r /build/requirements.txt

FROM python:3.12-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="argus-drift-monitor" \
      org.opencontainers.image.description="ARGUS KS/Evidently drift monitor"

RUN apt-get update && apt-get install -y --no-install-recommends \
    tini curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 argus \
    && useradd --uid 10001 --gid argus --create-home --shell /usr/sbin/nologin argus

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=argus:argus drift-monitor/ /app/drift-monitor/
COPY --chown=argus:argus ingestion/simulator/avro_codec.py /app/ingestion/simulator/avro_codec.py
COPY --chown=argus:argus ingestion/simulator/__init__.py /app/ingestion/simulator/__init__.py
COPY --chown=argus:argus ingestion/__init__.py /app/ingestion/__init__.py
COPY --chown=argus:argus shared/avro/ /app/shared/avro/
COPY --chown=argus:argus shared/gen/python/ /app/shared/gen/python/

RUN mkdir -p /app/drift-monitor/reports \
    && chown -R argus:argus /app/drift-monitor/reports

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/drift-monitor:/app:/app/shared/gen/python \
    ARGUS_AVRO_SCHEMA_PATH=/app/shared/avro/telemetry_event.avsc \
    DRIFT_REPORTS_DIR=/app/drift-monitor/reports \
    DRIFT_HEALTH_PORT=8094 \
    DRIFT_METRICS_PORT=8095

EXPOSE 8094 8095
USER argus

HEALTHCHECK --interval=20s --timeout=5s --start-period=40s --retries=5 \
  CMD curl -fsS http://127.0.0.1:8094/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "/app/drift-monitor/main.py"]
