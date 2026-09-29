# This is the copilot-backend's image (the primary application service),
# kept at the repository root to match the required submission layout.
# The alarm-api, alarm-management MCP server, and frontend each have their
# own scoped Dockerfile (apps/alarm-api/Dockerfile,
# mcp-servers/alarm-management/Dockerfile, apps/frontend/Dockerfile) because
# this is a multi-service system; docker-compose.yml builds and wires all
# four together -- see README.md "Quick start".
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
