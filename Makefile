.PHONY: help up down build logs test test-coverage ingest lint fmt run-alarm-api run-mcp run-backend run-frontend

help:
	@echo "Common targets:"
	@echo "  make up             - docker compose up --build (all services)"
	@echo "  make down           - stop and remove containers"
	@echo "  make build          - build all docker images"
	@echo "  make logs           - tail logs from all services"
	@echo "  make ingest         - build the RAG retrieval index locally"
	@echo "  make test           - run the full pytest suite locally"
	@echo "  make test-coverage  - run tests with coverage (html + terminal)"
	@echo "  make run-alarm-api  - run the Alarm Management API simulator locally"
	@echo "  make run-mcp        - run the alarm-management MCP server locally"
	@echo "  make run-backend    - run the copilot backend locally"
	@echo "  make run-frontend   - run the Streamlit GUI locally"

up:
	docker compose up --build

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

ingest:
	python -m rag.ingestion.index_builder --documents ./rag/documents --index ./rag/index/local

test:
	PYTHONPATH=. pytest tests/ rag/tests/ -v

test-coverage:
	PYTHONPATH=. pytest tests/ rag/tests/ \
		--cov=apps/backend --cov=connectors --cov=app --cov=server --cov=rag/ingestion --cov=rag/retrieval \
		--cov-report=term-missing --cov-report=html:docs/coverage_html

run-alarm-api:
	cd apps/alarm-api && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

run-mcp:
	cd mcp-servers/alarm-management && PYTHONPATH=../.. python -m server.app

run-backend:
	PYTHONPATH=. uvicorn apps.backend.main:app --host 0.0.0.0 --port 8080 --reload

run-frontend:
	cd apps/frontend && streamlit run app.py
