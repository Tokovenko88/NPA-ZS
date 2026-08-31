# Import

Import NPA JSON files into MySQL database.

## Usage

```
/kilo:import <json_path>
```

## Behavior

1. Load JSON from `data/input/` or provided path.
2. Connect to MySQL using `src/db/connection.py`.
3. Run `NpaImporter.import_file()`.
4. Log results to `data/logs/`.
5. Report inserted/updated records.
