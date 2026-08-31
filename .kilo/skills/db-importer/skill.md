# DB Importer Skill

Import NPA JSON into MySQL database.

## Trigger

Use when user asks to import, load to database, or sync DB.

## Procedure

1. Validate JSON schema.
2. Load `src/db/connection.py` config.
3. Run `NpaImporter.import_file()`.
4. Handle errors and retries.
5. Log statistics.

## References

- `src/db/importer.py`
- `src/db/connection.py`
- `docs/db_schema.md`
