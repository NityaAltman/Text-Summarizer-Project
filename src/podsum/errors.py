"""Exception hierarchy.

One base class means the CLI can catch `PodsumError` and print something a human
can act on, while any other exception escapes as a traceback because it is a bug.
"""


class PodsumError(Exception):
    """Base for every failure this tool expects to happen in normal use."""


class InvalidURL(PodsumError):
    """The input was not something we can extract a YouTube video ID from."""


class TranscriptUnavailable(PodsumError):
    """No usable captions: disabled, missing in the requested languages, or blocked."""


class LLMUnavailable(PodsumError):
    """The model backend could not be reached or refused the request."""


class LLMBadOutput(PodsumError):
    """The model returned something that does not fit the expected schema."""


class ConfigError(PodsumError):
    """The config file is missing, malformed, or has an unknown override key."""
