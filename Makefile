.PHONY: install fetch digest run test clean

# Load .env if it exists
-include .env
export

install:
	pip install -e ".[all]"

fetch:
	python scripts/fetch_test.py

digest:
	GIT_PUSH=false python -m argus.runner

run:
	python -m argus.runner

test:
	pytest tests/ -v

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -name "*.pyc" -delete 2>/dev/null; true
