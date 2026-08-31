# Report

Generate processing report.

## Usage

```
/kilo:report [--run-id <id>]
```

## Behavior

1. Collect stats from `data/debug_runs/` or last run.
2. Generate Markdown report with stage results, errors, timings.
3. Save to `data/work_tools/report.md`.
