# Agent Instructions for NPA-ZS

You are operating inside the NPA-ZS harness. Follow these rules.

## Project Layout

- `src/` — all Python source code
- `src/core/` — HTML parser, MODX processor
- `src/revision/` — revision engine and AI pipeline
- `src/compare/` — NPA revision comparison: our RTF vs legal-system document (DOCX/DOC/RTF), AI agent + Markdown report
- `src/db/` — database importer and editors
- `src/site/` — PHP/JS/CSS for website output
- `src/site/php/npazs/` — modular PHP source of truth for the `HtmlFromNpaZS` snippet (entry point = build recipe, AJAX, ~21 modules; map and agent rules in its `README.md`). `src/site/php/snippet.php` is GENERATED from these modules by `make build-snippet` — never edit it directly
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
- `npazs.compare.runner`

## Execution Rules

1. Never modify `data/base/` JSON files directly.
2. Work on copies in `data/input/` and write results to `data/output/`.
3. Validate JSON against schema before and after changes.
4. Log all operations to `data/logs/`.
5. Run `make validate` after structural changes.
6. Website PHP is edited only in `src/site/php/npazs/` modules (see its `README.md`); after edits run `make build-snippet` to regenerate `src/site/php/snippet.php` — the single script deployed into the MODX `HtmlFromNpaZS` snippet.
7. The revision pipeline (`run_all`) writes its artifacts **next to the target NPA file**
   (not in `data/output/`): `<number>_work.json` (cached AI stage answers),
   `<number>_log.md` (program work log: run metadata + change-tracker summary + full
   operation log), and `<orig>_<orig_date>_izm_<change>_<change_date>.json` (the
   resulting NPA). `<number>` is the amending NPA's cleaned `npa_number`, so `_work.json`
   and `_log.md` always share the same prefix for one run.
8. The compare module (`src/compare/`) writes reports/checkpoints to
   `data/output/compare/` and logs to `data/logs/compare_*.log`; it reads
   `data/base/` read-only (rule 1 applies).

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
