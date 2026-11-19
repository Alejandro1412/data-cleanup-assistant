.PHONY: install backend frontend test lint sample evaluate

install:
	cd backend && python -m venv .venv && .venv/bin/pip install -e ".[dev]"
	cd frontend && npm install

backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

test:
	cd backend && .venv/bin/pytest
	cd frontend && npm run build

lint:
	cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy app
	cd frontend && npm run lint

sample:
	cd backend && .venv/bin/python -m scripts.generate_dataset --rows 500 --out ../sample_data
	cp sample_data/customers_dirty.csv frontend/public/sample-customers.csv

evaluate:
	cd backend && .venv/bin/python -m scripts.evaluate --data ../sample_data
