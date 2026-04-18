.PHONY: dev test test-integration migrate fixtures typecheck lint format

dev:
	docker compose up --build

test:
	cd agent && ruff check src tests && ruff format --check src tests
	cd agent && mypy src
	cd agent && pytest tests/unit -q --cov=agent --cov-report=term-missing
	cd dashboard && npm run typecheck
	cd dashboard && npm run lint

test-integration:
	cd agent && pytest tests/integration -q

migrate:
	cd agent && alembic upgrade head

fixtures:
	cd agent && python ../scripts/load-fixtures.py

typecheck:
	cd agent && mypy src
	cd dashboard && npm run typecheck

lint:
	cd agent && ruff check src tests
	cd dashboard && npm run lint

format:
	cd agent && ruff format src tests
	cd dashboard && npx prettier --write .
