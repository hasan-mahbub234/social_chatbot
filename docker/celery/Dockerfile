FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/base.txt requirements/prod.txt ./requirements/
RUN pip install --no-cache-dir -r requirements/prod.txt

COPY . .

RUN useradd -m -u 1000 celeryuser && chown -R celeryuser:celeryuser /app
USER celeryuser

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV C_FORCE_ROOT=false

CMD ["celery", "-A", "app.workers.celery_config", "worker", "--loglevel=info", "--concurrency=4", "-Q", "ai_processing,embeddings,governance,risk_assessment,hallucination,voice,analytics,cleanup,escalation"]
