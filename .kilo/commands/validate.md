# Validate

Validate NPA JSON structure and DB integrity.

## Usage

```
/kilo:validate [--json <path>] [--db]
```

## Behavior

1. If `--json`: validate JSON against schema in `docs/json_schema.md`.
2. If `--db`: check DB tables, constraints, and revision consistency.
3. Report errors and warnings.
