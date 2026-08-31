# Revision Engine Skill

Apply AI-powered changes to NPA JSON.

## Trigger

Use when user asks to revise, apply changes, amend, or modify NPA.

## Procedure

1. Load target and amending JSON.
2. Run 5-stage pipeline via `npazs.revision.pipeline.orchestrator`.
3. Stage 1: revocation analysis.
4. Stage 2: dates and retroactivity.
5. Stage 3: extract changes.
6. Stage 4: HTML processing via Ollama.
7. Stage 5: rebuild revisions.
8. Validate and save result.

## References

- `src/revision/pipeline/`
- `src/revision/engine.py`
- `data/prompts/`
