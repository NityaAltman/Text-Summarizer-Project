"""Getting a timestamped transcript out of a YouTube URL.

This is the layer that touches the outside world, so it is also the layer that
breaks. Everything downstream of here is pure functions over data.
"""

from .captions import fetch_transcript
from .urls import extract_video_id

__all__ = ["extract_video_id", "fetch_transcript"]
