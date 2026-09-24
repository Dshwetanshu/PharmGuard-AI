# PharmGuard API (FastAPI) for local runs and Hugging Face Spaces (port 7860).
#
#   docker build -t pharmguard-api .
#   docker run --rm -p 7860:7860 -v "$PWD/data/profiles/public:/data/public:ro" pharmguard-api
#
# The image holds no data. It reads the processed build from PHARMGUARD_DATA_DIR
# (default /data/public), or downloads and verifies it at start-up when
# PHARMGUARD_HF_DATASET / _REVISION / _PROVENANCE_SHA256 and HF_TOKEN are set.
# Without a verified public build, /health reports why and /v1/check returns 503.

# python:3.11-slim, multi-arch index digest (linux/amd64 + linux/arm64), pinned 2026-09-24
FROM python:3.11-slim@sha256:da047cb8f9d1d98e5c070f5300ba9f7274e33b8fc0e5be5ed88740aed1b95ba9

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PHARMGUARD_DATA_DIR=/data/public \
    PHARMGUARD_REQUIRED_PROFILE=public \
    PHARMGUARD_RXNORM_API_ENABLED=false \
    PHARMGUARD_TRACING=none \
    HF_HOME=/tmp/hf

WORKDIR /app
COPY requirements-api.lock .
RUN pip install --require-hashes --no-deps -r requirements-api.lock

# Hugging Face Spaces runs containers as UID 1000.
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin pharmguard \
    && mkdir -p /data && chown pharmguard:pharmguard /data

COPY --chown=pharmguard:pharmguard src/ ./src/
COPY --chown=pharmguard:pharmguard api/ ./api/

USER pharmguard
EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:7860/health', timeout=4).status == 200 else 1)"]

# --no-proxy-headers: client IPs come only from api.ratelimit.client_ip (trusted hops).
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "7860", "--no-access-log", "--no-proxy-headers", "--timeout-graceful-shutdown", "10"]
