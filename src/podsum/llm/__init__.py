"""The model backend, behind one small interface.

Everything above this package talks to `LLMClient` and never imports `ollama.py`
directly. That is what makes swapping in a hosted API later a new file here plus one
line of config, rather than a refactor.
"""

from .base import LLMClient
from .factory import build_client

__all__ = ["LLMClient", "build_client"]
