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

## Quick Start

```bash
python -m pip install -r requirements.txt
python scripts/run_parser.py      # HTML → JSON
python scripts/run_importer.py    # JSON → DB
python scripts/run_revision.py    # Apply changes
python scripts/run_site_sync.py   # Sync to site
```

## Data

- `data/input/` — source and target NPA JSON
- `data/output/` — result JSON
- `data/base/` — base JSON files (laws/resolutions)
- `data/prompts/` — AI pipeline prompts
- `data/stage_answers/` — cached AI answers
- `data/debug_runs/` — debug artifacts

## Documentation

See `docs/` for schema, DB, site output, and pipeline docs.
See `instructions/` for modular agent instructions.
