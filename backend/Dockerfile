# KAI backend (FastAPI). Built from the repository root — see docker-compose.yml.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# CPU-only PyTorch first, so sentence-transformers doesn't pull the multi-GB CUDA build.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install -r requirements.txt

# Pipeline code (src/) and the API (backend/). data/ is mounted at runtime, not copied.
COPY src/ src/
COPY backend/ backend/

WORKDIR /app/backend
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
