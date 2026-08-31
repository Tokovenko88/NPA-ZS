# Parse

Parse HTML NPA document into structured JSON.

## Usage

```
/kilo:parse <html_path_or_url>
```

## Behavior

1. Load HTML from file or URL.
2. Run `NpaToJsonGenerator.generate_toc()`.
3. Save result to `data/output/<npa_id>_<date>.json`.
4. Log to `data/logs/parser.log`.
