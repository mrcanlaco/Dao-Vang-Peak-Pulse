# ============================================================
# Đảo Vàng — Dockerfile
# 3-stage: frontend (Vite build) → python builder (uv sync) → runtime
# Serves api_server.py (HTTP API + React static files) on port 8000
# ============================================================

# --- Stage 1: Frontend build (React + Vite) ---
FROM node:22-slim AS frontend

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# --- Stage 2: Python builder ---
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY src/ ./src/
COPY configs/ ./configs/
COPY scripts/ ./scripts/
COPY tests/ ./tests/

RUN uv sync --frozen

# --- Stage 3: Runtime ---
FROM python:3.12-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && git config --global --add safe.directory '*'

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/configs /app/configs
COPY --from=builder /app/scripts /app/scripts
COPY --from=builder /app/pyproject.toml /app/uv.lock ./

# Copy frontend dist vào frontend/dist (api_server.py serve từ đây)
COPY --from=frontend /frontend/dist /app/frontend/dist

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
# Keep OS-level tools and any third-party local-time calls aligned with the
# application's explicit Python/React timezone policy.
ENV TZ=Asia/Ho_Chi_Minh

RUN mkdir -p /app/data /app/artifacts

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

EXPOSE 8000

CMD ["python", "-m", "dao_vang.web.api_server"]
