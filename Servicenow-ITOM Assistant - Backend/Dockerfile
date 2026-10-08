# Deploy target: Render free-tier Docker Web Service (512 MB RAM).
#
# Memory notes (Oct 2026) - every line below that mentions memory is
# there because the service was being OOM-killed mid-request:
#  - No PyTorch any more. Embeddings run on ONNX Runtime via fastembed
#    (see ingestion/embeddings.py) - same model, same vectors, ~300 MB less.
#  - The MCP server now runs inside this process (agent/mcp_client.py),
#    not as a separate Python subprocess per call.
#  - retrieve.py no longer loads every chunk file into RAM.

FROM python:3.12-slim

# MALLOC_ARENA_MAX=2: glibc otherwise gives each thread its own memory
# arena. FastAPI runs sync endpoints on a thread pool, and those arenas
# hold on to freed memory, so RSS creeps up over time. Capping them is
# a standard fix for Python web apps on small containers.
ENV PYTHONUNBUFFERED=1 \
    MALLOC_ARENA_MAX=2 \
    FASTEMBED_CACHE_PATH=/app/.models

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the embedding model into this image layer at BUILD time
# (see prefetch_models.py) - keeps it out of every cold start.
COPY ingestion/embeddings.py ingestion/embeddings.py
COPY prefetch_models.py .
RUN python prefetch_models.py

# Now the actual application code (.dockerignore keeps PDFs, scratch
# files and secrets out of the image).
COPY . .

# Render sets $PORT dynamically at runtime - never hardcode 8000 in the
# command itself, only as the local-dev fallback below. One worker on
# purpose: every extra worker is a full second copy of the app in RAM.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
