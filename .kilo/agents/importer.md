# Importer Agent

Handles JSON → MySQL import.

## Responsibilities

- Validate JSON schema.
- Connect to MySQL.
- Run `NpaImporter.import_file()`.
- Handle duplicates, revisions, notes.
- Report import statistics.

## Tools

- `read` / `write` — JSON ops
- `bash` — DB migrations, checks

## Constraints

- Always use transactions.
- Rollback on critical errors.
- Never expose credentials in logs.
