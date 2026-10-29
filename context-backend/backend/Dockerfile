# ContextAPI backend image: API, Celery workers and migrations share it.
# Python is pinned to match .python-version.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/models/huggingface

RUN apt-get update \
    && apt-get install -y --no-install-recommends libmagic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU-only torch: the default Linux wheel bundles CUDA (several GB) that a
# CPU deployment never uses. The pinned torch version is kept.
COPY requirements.txt .
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

COPY . .

RUN useradd --create-home --uid 10001 app \
    && mkdir -p /models/huggingface \
    && chown -R app:app /app /models
USER app

EXPOSE 8000

# While workers embed and OCR, the CPU is saturated and an API worker can take
# longer than uvicorn's default 5 s to answer the supervisor's health check;
# it was then killed and its open requests dropped. 30 s still replaces a
# genuinely hung worker.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--timeout-worker-healthcheck", "30"]
