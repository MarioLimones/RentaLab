FROM node:24.13.0-bookworm-slim AS frontend-build

WORKDIR /build/frontend
RUN npm install --global npm@11.12.1
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12.15-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    RENTALAB_ENVIRONMENT=production \
    RENTALAB_DATABASE_URL=sqlite:////data/rentalab.db \
    RENTALAB_FRONTEND_DIST=/app/frontend/dist \
    RENTALAB_PORT=8000 \
    RENTALAB_SQLITE_BUSY_TIMEOUT_MS=5000 \
    RENTALAB_FORWARDED_ALLOW_IPS=127.0.0.1

WORKDIR /app/backend
COPY backend/requirements.lock ./
RUN python -m pip install --no-cache-dir --require-hashes -r requirements.lock \
    && groupadd --gid 10001 rentalab \
    && useradd --uid 10001 --gid rentalab --no-create-home rentalab \
    && mkdir -p /data \
    && chown 10001:10001 /data \
    && chmod 0700 /data

COPY backend/rentalab ./rentalab
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./
COPY --from=frontend-build /build/frontend/dist /app/frontend/dist
RUN chmod -R a-w /app

USER 10001:10001
EXPOSE 8000
VOLUME /data

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('RENTALAB_PORT', '8000') + '/health', timeout=2)" || exit 1

CMD ["python", "-m", "rentalab.start"]
