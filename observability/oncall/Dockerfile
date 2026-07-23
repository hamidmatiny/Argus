# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm
WORKDIR /app
COPY report_generator.py /app/report_generator.py
ENV ONCALL_ADDR=0.0.0.0:8100
EXPOSE 8100
USER nobody
CMD ["python", "-u", "/app/report_generator.py"]
