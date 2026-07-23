# syntax=docker/dockerfile:1
# ARGUS orchestration — Dagster webserver / daemon

FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY orchestration/requirements.txt /build/requirements.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r /build/requirements.txt

FROM python:3.12-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="argus-orchestration" \
      org.opencontainers.image.description="ARGUS Dagster + MLflow orchestration"

RUN apt-get update && apt-get install -y --no-install-recommends \
    tini curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 argus \
    && useradd --uid 10001 --gid argus --create-home --shell /usr/sbin/nologin argus

WORKDIR /opt/dagster/app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=argus:argus orchestration/ /opt/dagster/app/
COPY --chown=argus:argus lakehouse/common /opt/dagster/app/lakehouse_common

RUN mkdir -p /opt/dagster/storage /opt/dagster/app/artifacts \
        /opt/dagster/app/feature_store/data \
    && chown -R argus:argus /opt/dagster

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/opt/dagster/app \
    DAGSTER_HOME=/opt/dagster/app \
    ORCH_ARTIFACTS_DIR=/opt/dagster/app/artifacts \
    FEAST_REPO_PATH=/opt/dagster/app/feature_store

EXPOSE 3000
USER argus

HEALTHCHECK --interval=20s --timeout=5s --start-period=40s --retries=5 \
  CMD curl -fsS http://127.0.0.1:3000/server_info || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["dagster-webserver", "-h", "0.0.0.0", "-p", "3000", "-w", "workspace.yaml"]
