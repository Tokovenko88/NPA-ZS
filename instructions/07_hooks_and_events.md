# Hooks and Events

## Available Hooks

- `pre-commit` — lint, typecheck, tests, validate
- `pre-revision` — backup target JSON
- `post-revision` — validate result, generate report
- `pre-sync` — dry-run DB diff
- `post-sync` — verify cache

## Usage

Hooks are shell scripts in `.kilo/hooks/`. They are invoked automatically by the CLI or can be run manually.

## Adding Hooks

1. Create executable `.sh` in `.kilo/hooks/`.
2. Accept arguments via `$1`, `$2`, etc.
3. Exit 0 on success, non-zero on failure.
