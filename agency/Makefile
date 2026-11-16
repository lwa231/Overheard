# `make ci` is the whole gate: lint, unit tests, end-to-end smoke.
PY ?= python3
RUFF ?= $(shell command -v ruff 2>/dev/null || echo /root/.local/bin/ruff)

.PHONY: ci lint test smoke run
ci: lint test smoke

lint:
	$(RUFF) check .

test:
	$(PY) -m pytest -q

smoke:
	$(PY) scripts/smoke.py

run:
	PYTHONPATH=src $(PY) -m agency
