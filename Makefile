PYTHON ?= python3

.PHONY: test compile lint check check-all run

test:
	$(PYTHON) -m unittest discover -s tests -v

compile:
	$(PYTHON) -m compileall main.py bot services utils core config.py tests

lint:
	@command -v ruff >/dev/null 2>&1 || { echo "ruff is not installed. Install dev tools with: pip install -r requirements-dev.txt"; exit 1; }
	ruff check .

check: test compile

check-all: lint check

run:
	$(PYTHON) main.py
