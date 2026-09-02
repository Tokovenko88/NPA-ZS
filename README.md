# NPA-ZS

Harmonized legislative act processing pipeline for the Legislative Assembly of Sevastopol.

## Overview

NPA-ZS is a full-cycle harness for working with normative legal acts (NLAs):
- **Parse** HTML from sevzakon.ru into structured JSON
- **Import** JSON directly into MySQL database
- **Revise** NPA JSON using a 5-stage AI pipeline with local LLM
- **Sync** database content to website output via PHP/JS/CSS

## Modules

| Module | Path | Description |
|--------|------|-------------|
| Core parser | `src/core/` | HTML → JSON conversion, MODX integration |
| Revision engine | `src/revision/` | 5-stage AI pipeline, element finder, change applier |
| Database | `src/db/` | JSON → MySQL import, DB editors |
| Site output | `src/site/` | PHP snippet, JS viewer, CSS styles |
| UI | `src/ui/` | Tkinter applications |
| Config | `src/config/` | Settings for DB, MODX, Ollama |
| Compare | `src/compare/` | RTF/DOCX/DOC comparison of NPA revisions with AI agent |

## Quick Start

```bash
python -m pip install -r requirements.txt
python scripts/run_parser.py      # HTML → JSON
python scripts/run_importer.py    # JSON → DB
python scripts/run_revision.py    # Apply changes
python scripts/run_compare.py     # Compare our RTF vs legal-system document
python scripts/run_site_sync.py   # Sync to site
```

## Data

- `data/input/` — source and target NPA JSON
- `data/output/` — result JSON
- `data/output/compare/` — comparison reports (Markdown) + checkpoints
- `data/base/` — base JSON files (laws/resolutions)
- `data/prompts/` — AI pipeline prompts
- `data/stage_answers/` — cached AI answers
- `data/debug_runs/` — debug artifacts
- `data/logs/` — runtime logs (`last_run.log`, `last_paths.json`)

## Revision output artifacts

When applying changes (`make run-revision` / `npazs revise --source ... --target ...`),
the pipeline writes the following files next to the **target** NPA (the file being
modified), keyed by the amending NPA number:

| File | Contents |
|------|----------|
| `<number>_work.json` | Cached AI stage answers + run info (model, backend, timestamps) |
| `<number>_log.md` | Program work log: run metadata, change tracker summary, full operation log |
| `<orig>_<orig_date>_izm_<change>_<change_date>.json` | Resulting NPA JSON with applied changes |
| `FAILED_<orig>_..._izm_<change>_....json` | Result JSON saved on a failed run (with `_failed_run_report`) |

`<number>` is the amending NPA's cleaned number (`npa_number`), so `_work.json`
and `_log.md` always share the same prefix for a given run.

## Documentation

See `docs/` for schema, DB, site output, and pipeline docs.
See `instructions/` for modular agent instructions.
