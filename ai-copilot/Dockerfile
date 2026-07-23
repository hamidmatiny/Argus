# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl \
  && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONPATH=/app
ENV COPILOT_ADDR=:8090
EXPOSE 8090
HEALTHCHECK --interval=15s --timeout=5s --retries=5 --start-period=30s \
  CMD curl -fsS http://127.0.0.1:8090/health || exit 1
CMD ["sh", "-c", "python -m ingestion.index || true; python -m agent.app"]
