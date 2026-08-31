# Parser Agent

Handles HTML → JSON parsing.

## Responsibilities

- Load HTML from sevzakon.ru or local files.
- Run `NpaToJsonGenerator`.
- Detect structural elements, tables, appendices.
- Handle ambiguity dialogs.
- Save structured JSON to `data/output/`.

## Tools

- `read` / `write` — file operations
- `browser_*` — fetch URLs if needed
- `bash` — run parser scripts

## Constraints

- Preserve original HTML in debug logs.
- Do not modify `data/base/`.
