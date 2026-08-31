# JSON Parser Skill

Parse HTML legislative documents into structured JSON.

## Trigger

Use when user asks to parse HTML, convert document, or extract structure.

## Procedure

1. Load HTML from `data/input/` or URL.
2. Initialize `npazs.core.html_parser.NpaToJsonGenerator`.
3. Run `generate_toc()`.
4. Validate output JSON.
5. Save to `data/output/`.

## References

- `src/core/html_parser.py`
- `docs/json_schema.md`
- `data/prompts/`
