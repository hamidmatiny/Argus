# syntax=docker/dockerfile:1
# Build from the monorepo root:
#   docker build -f infra/terraform/modules/serverless-etl/lambda/Dockerfile \
#     -t <ecr-url>:latest .
FROM public.ecr.aws/lambda/python:3.12

COPY infra/terraform/modules/serverless-etl/lambda/requirements.txt /tmp/lambda-requirements.txt
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r /tmp/lambda-requirements.txt

# Shared contracts (Pandera gate) and simulator — same sources as the Kafka path.
COPY shared/contracts/v1/ ${LAMBDA_TASK_ROOT}/v1/
COPY ingestion/__init__.py ${LAMBDA_TASK_ROOT}/ingestion/__init__.py
COPY ingestion/simulator/ ${LAMBDA_TASK_ROOT}/ingestion/simulator/

COPY infra/terraform/modules/serverless-etl/lambda/common.py ${LAMBDA_TASK_ROOT}/common.py
COPY infra/terraform/modules/serverless-etl/lambda/generate_handler.py ${LAMBDA_TASK_ROOT}/generate_handler.py
COPY infra/terraform/modules/serverless-etl/lambda/validate_handler.py ${LAMBDA_TASK_ROOT}/validate_handler.py
COPY infra/terraform/modules/serverless-etl/lambda/sync_handler.py ${LAMBDA_TASK_ROOT}/sync_handler.py
COPY infra/terraform/modules/serverless-etl/lambda/dlq_handler.py ${LAMBDA_TASK_ROOT}/dlq_handler.py

ENV PYTHONPATH=${LAMBDA_TASK_ROOT}
WORKDIR ${LAMBDA_TASK_ROOT}
