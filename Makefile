.PHONY: install dev lint typecheck test test-cov clean docker-build docker-up db-migrate

# ─── Installation ────────────────────────────────────────────────────────────

install:
	pip install -e "."

dev:
	pip install -e ".[dev]"
	pre-commit install

# ─── Quality ─────────────────────────────────────────────────────────────────

lint:
	ruff format --check src/kitty tests/
	ruff check src/kitty tests/

typecheck:
	mypy src/kitty/

# ─── Testing ─────────────────────────────────────────────────────────────────

test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov --cov-report=term --cov-report=html

# ─── Housekeeping ────────────────────────────────────────────────────────────

clean:
	rm -rf dist/ build/ *.egg-info/ .mypy_cache/ .ruff_cache/ .pytest_cache/
	rm -rf htmlcov/ .coverage coverage.xml
	rm -rf __pycache__/ */__pycache__/ */*/__pycache__/
	rm -rf *.pyc */*.pyc */*/*.pyc
	rm -rf .venv/

# ─── Docker ──────────────────────────────────────────────────────────────────

docker-build:
	docker build -t kitty-llm .

docker-up:
	docker compose up -d

# ─── Database ────────────────────────────────────────────────────────────────

db-migrate:
	alembic upgrade head
