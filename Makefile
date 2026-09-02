.PHONY: help install lint typecheck test validate clean run-parser run-revision run-compare run-importer run-sync build-snippet

help:
	@echo NPA-ZS make targets:
	@echo   install       - install dependencies
	@echo   lint          - run ruff
	@echo   typecheck     - run mypy
	@echo   test          - run pytest
	@echo   validate      - validate JSON schemas
	@echo   run-parser    - run HTML parser GUI
	@echo   run-revision  - run revision processor GUI
	@echo   run-compare   - run NPA revision comparison GUI
	@echo   run-importer  - run DB importer GUI
	@echo   run-sync      - run site sync
	@echo   build-snippet - assemble src/site/php/snippet.php from npazs/ modules
	@echo   clean         - remove caches and build artifacts

install:
	python -m pip install -r requirements.txt

lint:
	ruff check src/ scripts/ tests/

typecheck:
	mypy src/ scripts/

test:
	pytest tests/ -v

validate:
	python scripts/validate.py

run-parser:
	python scripts/run_parser.py

run-revision:
	python scripts/run_revision.py

run-compare:
	python scripts/run_compare.py

run-importer:
	python scripts/run_importer.py

run-sync:
	python scripts/run_site_sync.py

build-snippet:
	python data/work_tools/build_snippet.py

clean:
	rm -rf .ruff_cache .pytest_cache __pycache__ dist build
