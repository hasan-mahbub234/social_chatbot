FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    postgresql-client curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/base.txt requirements/prod.txt ./requirements/
RUN pip install --no-cache-dir -r requirements/prod.txt

COPY . .

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
