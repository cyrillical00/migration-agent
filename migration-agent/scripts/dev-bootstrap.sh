#!/usr/bin/env bash
set -euo pipefail

echo "==> Checking tool versions"

python_version=$(python3 --version 2>&1 | awk '{print $2}')
required_python="3.12"
if [[ "$python_version" < "$required_python" ]]; then
  echo "ERROR: Python $required_python+ required, got $python_version"
  exit 1
fi

node_version=$(node --version 2>&1 | sed 's/v//')
required_node="20"
if [[ "${node_version%%.*}" -lt "$required_node" ]]; then
  echo "ERROR: Node $required_node+ required, got $node_version"
  exit 1
fi

docker --version > /dev/null 2>&1 || { echo "ERROR: Docker not found"; exit 1; }
terraform --version > /dev/null 2>&1 || echo "WARNING: Terraform not found (needed for infra work only)"

echo "==> Copying .env.example -> .env (if missing)"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "  .env created. Fill in real values before running."
fi

echo "==> Pulling Docker images"
docker compose pull --ignore-buildable

echo "==> Starting postgres"
docker compose up -d postgres

echo "==> Waiting for postgres to be healthy"
until docker compose exec postgres pg_isready -U postgres -q; do
  sleep 1
done

echo "==> Running Alembic migrations"
cd agent && alembic upgrade head && cd ..

echo "==> Loading fixtures"
python scripts/load-fixtures.py

echo "==> Starting full stack"
docker compose up --build
