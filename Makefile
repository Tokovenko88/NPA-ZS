.PHONY: help install lint typecheck test validate clean run-parser run-editor run-revision run-compare run-verify run-importer run-sync run-free-deepseek auth-free-deepseek run-qwen2api setup-qwen2api build-snippet

help:
	@echo NPA-ZS make targets:
	@echo   install       - install dependencies
	@echo   lint          - run ruff
	@echo   typecheck     - run mypy
	@echo   test          - run pytest
	@echo   validate      - validate JSON schemas
	@echo   run-parser    - run HTML parser GUI
	@echo   run-editor    - run DB records editor GUI
	@echo   run-revision  - run revision processor GUI
	@echo   run-compare   - run NPA revision comparison GUI
	@echo   run-verify    - run verification GUI
	@echo   run-importer  - run DB importer GUI
	@echo   run-sync      - run site sync
	@echo   build-snippet - assemble src/site/php/snippet.php from npazs/ modules
	@echo   setup-qwen2api - install/configure local Qwen2API proxy
	@echo   run-qwen2api  - start local Qwen2API proxy
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

run-editor:
	python scripts/run_editor.py

run-revision:
	python scripts/run_revision.py

run-compare:
	python scripts/run_compare.py

run-verify:
	python scripts/run_verify.py

run-importer:
	python scripts/run_importer.py

run-sync:
	python scripts/run_site_sync.py

run-free-deepseek:
	python scripts/setup_free_deepseek.py --start

auth-free-deepseek:
	python scripts/setup_free_deepseek.py

setup-qwen2api:
	python scripts/setup_qwen2api.py

run-qwen2api:
	python scripts/setup_qwen2api.py --start

build-snippet:
	python data/work_tools/build_snippet.py

clean:
	rm -rf dist build
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \) -prune -exec rm -rf {} +
