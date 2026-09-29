# Build context is the repository root (see docker-compose.yml) because this
# service depends on the shared connectors/ package.
FROM python:3.11-slim

WORKDIR /app

COPY mcp-servers/alarm-management/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY connectors ./connectors
COPY mcp-servers/alarm-management/server ./server

ENV PYTHONPATH=/app

EXPOSE 9000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:9000/health', timeout=2)" || exit 1

CMD ["uvicorn", "server.asgi:app", "--host", "0.0.0.0", "--port", "9000"]
