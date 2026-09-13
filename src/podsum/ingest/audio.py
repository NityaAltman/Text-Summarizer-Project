"""Stage 5: local transcription for videos with no captions.

Deliberately unimplemented. It sits here as a named seam so that `pipeline.py` can
already branch on it, and so the shape of the eventual implementation is obvious:

    1. `yt-dlp` downloads bestaudio and `ffmpeg` converts it to 16kHz mono WAV.
    2. `faster-whisper` transcribes it, yielding segments with start/end times.
    3. Those segments map one-to-one onto our `Snippet` type.

Nothing downstream changes, because the rest of the pipeline only knows about
`Transcript`. That is the payoff of putting a type at the boundary.

Install the extra dependencies with:  pip install -e ".[audio]"
"""

from __future__ import annotations

from ..types import Transcript


def transcribe(video_id: str, model_size: str = "small") -> Transcript:
    raise NotImplementedError(
        "Local transcription is stage 5. Until then, podsum only handles videos "
        "that already have captions."
    )
