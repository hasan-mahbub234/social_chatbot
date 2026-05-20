.PHONY: install install-dev install-prod run worker beat flower migrate seed test lint clean docker-up docker-down

# ── Install ───────────────────────────────────────────────
# Development: includes Groq + sentence-transformers + testing tools
install-dev:
	pip install -r requirements/dev.txt

# Production: OpenAI only — no Groq, no sentence-transformers, no torch
install-prod:
	pip install -r requirements/prod.txt

# Default install = dev
install: install-dev

# ── Run ───────────────────────────────────────────────────
run:
	python run.py

# ── Celery ───────────────────────────────────────────────
worker:
	celery -A app.workers.celery_config worker --loglevel=info \
		-Q ai_processing,embeddings,crawler,governance,risk_assessment,hallucination,voice,analytics,cleanup,escalation

beat:
	celery -A app.workers.celery_config beat --loglevel=info

flower:
	celery -A app.workers.celery_config flower --port=5555

# ── Database ─────────────────────────────────────────────
migrate:
	alembic upgrade head

migrate-create:
	alembic revision --autogenerate -m "$(msg)"

seed:
	python scripts/seed_data.py

# ── Testing / Quality ────────────────────────────────────
test:
	pytest tests/ -v --cov=app --cov-report=term-missing

lint:
	ruff check app/
	mypy app/ --ignore-missing-imports

# ── Docker ───────────────────────────────────────────────
docker-up:
	docker-compose -f infrastructure/docker-compose.yml up -d

docker-down:
	docker-compose -f infrastructure/docker-compose.yml down

docker-logs:
	docker-compose -f infrastructure/docker-compose.yml logs -f

docker-build:
	docker-compose -f infrastructure/docker-compose.yml build

# ── Utilities ────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache

ingest:
	python scripts/ingest_documents.py $(dir) $(org_id)
