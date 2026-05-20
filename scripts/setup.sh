#!/bin/bash
set -e

echo "=== Enterprise AI Agent Platform Setup ==="

# Check Python version
python3 --version

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements/base.txt

# Copy env file
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from .env.example — please update with your values"
fi

echo "Setup complete. Run: source venv/bin/activate && uvicorn app.main:app --reload"
