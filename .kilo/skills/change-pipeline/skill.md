# Change Pipeline Skill

Extract and apply grouped changes from amending NPA.

## Trigger

Use during Stage 3-5 of revision pipeline.

## Procedure

1. Group changes by target element.
2. Resolve structural paths.
3. Apply changes via `apply_grouped_changes()`.
4. Rebuild affected elements.

## References

- `src/revision/change_pipeline.py`
- `src/revision/change_applier.py`
- `src/revision/revision_builder.py`
