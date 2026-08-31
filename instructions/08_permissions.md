# Permissions

## Levels

- `read` — inspect files
- `write` — modify source and data
- `deploy` — publish to site
- `db-admin` — database operations

## Configuration

Permissions are defined in `.kilo/permissions/*.yaml`.

## Enforcement

Agents must check permissions before write/deploy operations.
