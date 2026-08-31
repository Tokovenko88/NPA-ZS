# Site Renderer Skill

Render and synchronize NPA content to website.

## Trigger

Use when user asks to sync, publish, or update website.

## Procedure

1. Load NPA from DB.
2. Render HTML using site templates.
3. Upload via SFTP.
4. Update MODX TV parameters.
5. Invalidate cache.

## References

- `src/site/php/`
- `src/core/modx_processor.py`
- `docs/site_output.md`
