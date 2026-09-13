"""Allows `python -m podsum ...` as well as the installed `podsum` script."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
