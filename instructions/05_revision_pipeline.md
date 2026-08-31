# Revision Pipeline

## Stages

1. **Revocation Analysis** — find loss-of-force clauses.
2. **Dates Analysis** — find special dates and retroactive clauses.
3. **Changes Extraction** — extract add/delete/change/new_redaction operations.
4. **HTML Processing** — compute new HTML via Ollama with highlights.
5. **Rebuild** — create new revisions, update tree.

## Execution

Use `npazs.revision.pipeline.orchestrator.run_pipeline()`.

## Determinism

- Same input → same output.
- All dates computed deterministically.
- No random choices.
