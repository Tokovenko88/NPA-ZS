# Sync

Synchronize database content to website (MODX).

## Usage

```
/kilo:sync <npa_id>
```

## Behavior

1. Load NPA from DB via `src/db/importer.py`.
2. Render HTML via `src/site/php/snippet.php` logic.
3. Upload JSON and static HTML via `src/core/modx_processor.py`.
4. Update MODX TV parameters.
5. Invalidate cache.
