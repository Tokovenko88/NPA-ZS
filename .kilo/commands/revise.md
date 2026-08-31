# Revise

Apply changes from amending NPA to target NPA using AI pipeline.

## Usage

```
/kilo:revise <target_json> <amending_json>
```

## Behavior

1. Load target and amending JSON from `data/input/`.
2. Run 5-stage AI pipeline via `src/revision/pipeline/orchestrator.py`.
3. Cache intermediate answers in `data/stage_answers/`.
4. Save result to `data/output/`.
5. Export debug run to `data/debug_runs/<timestamp>/`.
