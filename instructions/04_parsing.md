# Parsing Instructions

## HTML → JSON

1. Fetch HTML from sevzakon.ru or load local file.
2. Initialize `NpaToJsonGenerator`.
3. Call `generate_toc()` to parse structure.
4. Handle appendices, structured tables, duplicate numbers.
5. Save to `data/output/`.

## Ambiguity Handling

- Unknown hierarchy → ask user via dialog.
- Appendix title → confirm with user.
- Table structure → auto-detect or ask.

## Output Format

See `instructions/02_json_schema.md`.
