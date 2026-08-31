"""Позволяет запускать пакет как ``python -m npazs <команда>``."""

from npazs.main import main

if __name__ == "__main__":
    raise SystemExit(main())
