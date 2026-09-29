# Build context is the repository root (see docker-compose.yml) because this
# service depends on the shared rag/ package.
FROM python:3.11-slim

WORKDIR /app

COPY apps/backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/backend ./apps/backend
COPY rag ./rag

ENV PYTHONPATH=/app

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health', timeout=3)" || exit 1

CMD ["uvicorn", "apps.backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
