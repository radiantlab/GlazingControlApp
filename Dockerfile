FROM node:20-bookworm-slim AS web-build

WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SVC_DATA_DIR=data \
    WEB_DIST_DIR=/app/web/dist

WORKDIR /app/svc

COPY svc/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY svc/ ./
COPY --from=web-build /build/web/dist /app/web/dist

EXPOSE 8000
VOLUME ["/app/svc/data"]

CMD ["python", "main.py"]
