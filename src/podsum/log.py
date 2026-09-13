"""Logging setup.

Progress goes to stderr so that `podsum summarize URL > notes.md` produces a clean
markdown file while you still see what is happening.
"""

from __future__ import annotations

import logging
import sys

_FORMAT = "%(asctime)s  %(levelname)-7s %(name)-22s %(message)s"


def setup(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format=_FORMAT,
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    # httpx logs every request at INFO, which drowns out our own progress lines.
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get(name: str) -> logging.Logger:
    return logging.getLogger(name)
