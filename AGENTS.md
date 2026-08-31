# Agent Instructions for NPA-ZS

You are operating inside the NPA-ZS harness. Follow these rules.

## Project Layout

- `src/` — all Python source code
- `src/core/` — HTML parser, MODX processor
- `src/revision/` — revision engine and AI pipeline
- `src/db/` — database importer and editors
- `src/site/` — PHP/JS/CSS for website output
- `src/ui/` — Tkinter GUIs
- `data/` — runtime data, prompts, base JSON, logs
- `docs/` — technical documentation
- `scripts/` — entry points
- `tests/` — unit tests

## Canonical Import Paths

Always import from `npazs.*`:
- `npazs.core.html_parser`
- `npazs.revision.engine`
- `npazs.db.importer`
- `npazs.config.settings`

## Execution Rules

1. Never modify `data/base/` JSON files directly.
2. Work on copies in `data/input/` and write results to `data/output/`.
3. Validate JSON against schema before and after changes.
4. Log all operations to `data/logs/`.
5. Run `make validate` after structural changes.

## Permissions

- Read: any file in repo
- Write: `src/`, `data/input/`, `data/output/`, `data/work_tools/`, `data/logs/`, `data/stage_answers/`, `data/debug_runs/`
- Deploy: `src/site/`, `dist/`
- DB admin: `src/db/` only

## Hooks

Pre-commit: lint, typecheck, tests.
Pre-revision: backup target JSON.
Post-revision: validate result, generate report.
Pre-sync: dry-run DB diff.
