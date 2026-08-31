# Init

Initialize NPA-ZS project directories and configuration.

## Usage

```
/kilo:init
```

## Behavior

1. Ensure `data/input`, `data/output`, `data/logs`, `data/debug_runs`, `data/stage_answers`, `data/work_tools` exist.
2. Copy `.env.example` to `.env` if missing.
3. Run validation check on base JSON files in `data/base/`.
