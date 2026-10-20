# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/backend
WORKDIR /app
# Conversion tools are infrastructure only; upload/conversion business APIs remain separate work.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libreoffice-writer libreoffice-impress poppler-utils fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements-lock.txt backend/requirements-lock.txt
RUN python -m pip install --no-cache-dir -r backend/requirements-lock.txt
COPY backend/ backend/
RUN python -m pip install --no-cache-dir --no-deps ./backend && python -m pip check
COPY data/kb/ data/kb/
COPY deploy/bootstrap.py deploy/bootstrap.py
COPY --from=frontend /build/dist/ frontend/dist/
RUN useradd --create-home --uid 10001 learner \
    && mkdir -p data/index data/logs data/uploads \
    && chown -R learner:learner data
USER learner
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=90s --retries=6 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]
ENTRYPOINT ["python", "deploy/bootstrap.py"]
