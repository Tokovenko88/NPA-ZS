# Overview

NPA-ZS is a unified pipeline for processing normative legal acts (NLAs) of the Legislative Assembly of Sevastopol.

## Modules

- **Parser**: HTML → JSON (`src/core/`)
- **Importer**: JSON → MySQL (`src/db/`)
- **Reviser**: AI-powered change application (`src/revision/`)
- **Site Sync**: DB → website (`src/site/`)
- **UI**: Tkinter GUIs (`src/ui/`)

## Data Flow

```
HTML (sevzakon.ru)
    ↓ [Parser]
JSON
    ↓ [Importer]
MySQL
    ↓ [Reviser]
Modified JSON
    ↓ [Site Sync]
Website (MODX)
```

## Key Concepts

- **item_id**: Stable string ID for structural elements.
- **Revision**: Time-bound content change with `valid_from`/`valid_to`.
- **mod_type**: `add`, `change`, `new_redaction`, `delete`.
- **highlights**: JSON diff for visual comparison.
