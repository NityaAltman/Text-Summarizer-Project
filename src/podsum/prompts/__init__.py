"""Prompts live in `.md` files, not in Python string literals.

Three reasons, all of which you feel within a day of iterating:

* `git diff` on a prompt change is readable, so you can see what you actually altered.
* Editing a prompt does not mean touching code, so experiments stay cheap.
* The file's hash goes into the cache key, so changing a prompt automatically
  invalidates the summaries it produced. Nothing is more confusing than tweaking a
  prompt and seeing identical output because you forgot you cached it.
"""

from __future__ import annotations

import hashlib
from functools import cache
from importlib import resources


@cache
def load(name: str) -> str:
    """Read the prompt named `name` (without extension) from this package."""
    return resources.files(__package__).joinpath(f"{name}.md").read_text(encoding="utf-8")


def version(name: str) -> str:
    """A short hash of the prompt, used to key caches."""
    return hashlib.sha256(load(name).encode()).hexdigest()[:12]
