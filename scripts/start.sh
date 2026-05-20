#!/bin/bash
set -e

echo "Starting services..."
docker-compose -f infrastructure/docker-compose.yml up -d postgres redis
sleep 5
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
