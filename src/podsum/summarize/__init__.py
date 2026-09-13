"""Map-reduce summarization.

The pattern in one line: summarize each chunk independently (map), then summarize the
summaries (reduce). It is how every system that handles input longer than a context
window works, and it is the most transferable idea in this repository.
"""

from .mapper import summarize_chunks
from .reducer import reduce_summaries

__all__ = ["reduce_summaries", "summarize_chunks"]
