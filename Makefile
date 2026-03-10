.PHONY: install lint type-check test build clean

install:
	pip install -e ".[dev]"

lint:
	ruff check src/ tests/

lint-fix:
	ruff check --fix src/ tests/

type-check:
	mypy src/

test:
	pytest -v

test-cov:
	pytest --cov=agr_abc_document_parsers --cov-report=term-missing

build:
	python -m build

clean:
	rm -rf dist/ build/ *.egg-info src/*.egg-info .pytest_cache .mypy_cache .coverage htmlcov
