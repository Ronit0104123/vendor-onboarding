PY := backend/.venv/bin/python

setup:            ## install backend + frontend dependencies
	python3.11 -m venv backend/.venv
	backend/.venv/bin/pip install -r backend/requirements.txt
	cd frontend && npm ci

sample-data:      ## regenerate the fake documents, manifest and scenarios
	$(PY) sample_data/generate.py

seed:             ## create demo users + historical runs (idempotent)
	cd backend && .venv/bin/python -m app.seed

reset:            ## wipe the database and reseed
	cd backend && .venv/bin/python -m app.seed --reset

api:              ## backend on :8000 (runs the queue worker in-process)
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

web:              ## frontend dev server on :5173 (proxies /api to :8000)
	cd frontend && npm run dev

build:            ## production frontend build (served by the backend from frontend/dist)
	cd frontend && npm run build

test:             ## all backend tests, LLM mocked
	cd backend && .venv/bin/pytest -q

audit:            ## dependency vulnerability scans
	cd backend && .venv/bin/pip-audit -r requirements.txt
	cd frontend && npm audit

.PHONY: setup sample-data seed reset api web build test audit
