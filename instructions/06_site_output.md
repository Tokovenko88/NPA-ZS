# Site Output

## Rendering

PHP snippet reads from MySQL and renders HTML with:
- Document structure tree
- Revision history
- Comparison view
- Download button (RTF)

## Caching

Static HTML cached at:
`/assets/npa/{type}/{year}/{npa_id}/{npa_id}_{date}.html`

## Sync

Use `npazs.core.modx_processor.MODXHTMLProcessor` to:
- Upload JSON via SFTP
- Update TV parameters
- Invalidate cache
