# One entry point for everything. `make ci` is exactly what the CI pipeline runs.
PY ?= python3
-include board.conf
-include $(if $(SITE),sites/$(SITE).conf)
BOARD_USER ?= arduino
BOARD ?= $(BOARD_USER)@$(BOARD_HOST)

.PHONY: ci lint test sprites sprites-check demo deploy smoke app
ci: lint sprites-check test smoke

lint:
	ruff check .

test:
	$(PY) -m pytest -q

sprites:
	$(PY) tools/build_sprites.py

sprites-check:
	$(PY) tools/build_sprites.py --check

smoke:
	$(PY) scripts/smoke.py

demo:
	PYTHONPATH=src $(PY) -m overheard --demo --data-dir /tmp/overheard-demo

deploy: ci
	BOARD=$(BOARD) scripts/run.sh

app:
	$(PY) tools/build_app.py dist
