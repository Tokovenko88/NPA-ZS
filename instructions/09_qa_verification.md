# QA and Verification

## Checklist

- [ ] JSON validates against schema
- [ ] All `item_id` unique
- [ ] Revision chains are contiguous (no gaps)
- [ ] `modified_by_id` references exist
- [ ] DB foreign keys intact
- [ ] Site output renders without errors
- [ ] Cache invalidated after sync

## Commands

```bash
make validate
make test
make lint
make typecheck
```

## Debug Runs

Every revision run exports to `data/debug_runs/<timestamp>/` with:
- Target and amending JSON
- Stage answers
- Run log
