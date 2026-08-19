.PHONY: help setup test lint sim dryrun smoke slice clean

help:
	@echo "make setup   install deps into .venv"
	@echo "make test    run the test suite"
	@echo "make lint    ruff check"
	@echo "make sim     full loop on the simulated oracle (free, no API calls)"
	@echo "make dryrun  cost preflight only, dispatches nothing"
	@echo "make smoke   20 real probes, control arm only (~\$$0.20)"
	@echo "make slice   full 5-arm run, 60 mandates (~\$$3)"
	@echo "make clean   remove artifacts and caches"

setup:
	python3 -m venv .venv
	./.venv/bin/pip install -q --upgrade pip
	./.venv/bin/pip install -q -e ".[dev]"
	@echo "done. activate with: source .venv/bin/activate"

test:
	./.venv/bin/python -m pytest tests/ -q

lint:
	./.venv/bin/ruff check acop/ tests/ scripts/

sim:
	./.venv/bin/python -m scripts.run_simulated

smoke:
	./.venv/bin/python -m scripts.run_vertical_slice --smoke

dryrun:
	./.venv/bin/python -m scripts.run_vertical_slice --smoke --dry-run

slice:
	./.venv/bin/python -m scripts.run_vertical_slice --mandates 60

clean:
	rm -rf artifacts/raw artifacts/*.json artifacts/*.html
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
