import pytest

from podsum.errors import InvalidURL
from podsum.ingest.urls import extract_video_id

VIDEO_ID = "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "candidate",
    [
        VIDEO_ID,
        f"https://www.youtube.com/watch?v={VIDEO_ID}",
        f"http://youtube.com/watch?v={VIDEO_ID}",
        f"https://m.youtube.com/watch?v={VIDEO_ID}",
        f"youtube.com/watch?v={VIDEO_ID}",
        f"https://www.youtube.com/watch?v={VIDEO_ID}&t=42s&list=PLxyz",
        f"https://youtu.be/{VIDEO_ID}",
        f"https://youtu.be/{VIDEO_ID}?t=90",
        f"https://www.youtube.com/embed/{VIDEO_ID}",
        f"https://www.youtube.com/shorts/{VIDEO_ID}",
        f"https://www.youtube.com/live/{VIDEO_ID}",
        f"https://www.youtube-nocookie.com/embed/{VIDEO_ID}",
    ],
)
def test_accepts_every_common_form(candidate: str) -> None:
    assert extract_video_id(candidate) == VIDEO_ID


@pytest.mark.parametrize(
    "candidate",
    [
        "",
        "   ",
        "not a url",
        "https://vimeo.com/12345",
        "https://www.youtube.com/watch?v=tooshort",
        "https://www.youtube.com/",
        "https://youtu.be/",
    ],
)
def test_rejects_anything_without_an_id(candidate: str) -> None:
    with pytest.raises(InvalidURL):
        extract_video_id(candidate)


def test_surrounding_whitespace_is_ignored() -> None:
    assert extract_video_id(f"  https://youtu.be/{VIDEO_ID}  ") == VIDEO_ID
