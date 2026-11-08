# One image serves the API and the built frontend from the same origin (one public URL,
# strict SameSite cookies work, no CORS needed).

FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 ENV=prod
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY backend/ backend/
COPY sample_data/ sample_data/
COPY --from=web /web/dist frontend/dist
RUN useradd --create-home --uid 10001 app && mkdir -p backend/data backend/storage && chown -R app /app/backend/data /app/backend/storage
USER app
WORKDIR /app/backend
EXPOSE 8000
# Migrations run on startup; the seed is idempotent (creates demo users + history only once).
CMD ["sh", "-c", "python -m app.seed && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
