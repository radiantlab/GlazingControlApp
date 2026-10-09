# The base image versions must match .nvmrc and svc/.python-version, which CI
# tests against. A Dependabot bump here needs those files updated in the same PR.
FROM node:25-bookworm-slim AS web-build

WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.11-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    WEB_DIST_DIR=/app/web/dist \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app/svc

# Dependencies come from uv.lock, the same lock CI tests against. Installing
# them before copying the source keeps this layer cached across code changes.
COPY svc/pyproject.toml svc/uv.lock svc/README.md ./
RUN uv sync --frozen --no-dev --no-install-project --no-cache

COPY svc/ ./
# Routines run as `python3` subprocesses, so check that the python3 on PATH is
# the project venv with its runtime dependencies (requests among them).
RUN uv sync --frozen --no-dev --no-cache \
    && python3 -c "import requests, fastapi, pymodbus, serial"

COPY --from=web-build /build/web/dist /app/web/dist

EXPOSE 8000
VOLUME ["/app/svc/data"]

CMD ["python", "main.py"]
