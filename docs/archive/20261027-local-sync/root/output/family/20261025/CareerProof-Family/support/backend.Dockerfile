FROM public.ecr.aws/docker/library/python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/careerproof/backend
COPY backend/pyproject.toml backend/README.md ./
COPY backend/app ./app
RUN pip install --no-cache-dir .
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY backend/evals ./evals
COPY backend/scripts ./scripts
COPY demo /opt/careerproof/demo
ENV PYTHONPATH=/opt/careerproof/backend

LABEL org.opencontainers.image.revision=8ca91cc2c8e32fbd59412134798eb7db257a29d4

RUN apt-get update && apt-get install -y --no-install-recommends libxcb1 libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
