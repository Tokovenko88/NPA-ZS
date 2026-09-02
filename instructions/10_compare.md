# Compare Module

## Purpose

Cross-check the RTF produced by NPA-ZS against the same NPA document
produced by an external legal system (DOCX/DOC/RTF). Output is a
human-readable Markdown report of mismatches.

## Run

- GUI: `python scripts/run_compare.py` (or `make run-compare`)
- CLI: `npazs compare --ours ours.rtf --theirs theirs.docx [--output report.md] [--mode mechanical]`

## What is compared

1. Notes («Примечание:») — presence and effective dates only; placement and
   formatting are deliberately ignored (stylistics).
2. Body text — character-level diff per structural element, reported with the
   full element path (раздел -> глава -> статья -> часть -> пункт).

## Agent

For each mismatch the agent classifies the cause: `original_edition`,
`amendment`, `implementation_gap`, `technical_correction`, `formatting`,
`unclear` (prompt: `data/prompts/compare_prompt.md`).

- Script feeds the agent note context (linked NPA numbers, dates).
- For `amendment`/`implementation_gap` the script pulls the concrete change
  text from the JSON base by `source_item_id` (the `#` note link) or by
  element path (`npazs.compare.npa_resolver.extract_change_text`); if the
  element cannot be identified, the full amending NPA text is provided.
- For `technical_correction`/`original_edition` the element is checked
  against the original NPA edition in the base
  (`get_original_element_text`) — the legal system sometimes fixes the
  legislator's typos, our pipeline never does.

## Resume

Classification state is checkpointed to `<report>.checkpoint.json` after each
batch (fingerprint: file paths/sizes/mtimes + mode). Re-running with the same
inputs continues from the first unprocessed mismatch instead of starting over.
Artifacts: reports in `data/output/compare/`, logs in `data/logs/compare_*.log`.
