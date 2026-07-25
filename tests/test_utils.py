import pytest

from src.msoc.utils import validate_and_return_absolute_url  # type: ignore


@pytest.mark.parametrize(
    ("sound_url", "base_url", "expected"),
    [
        ("https://example.com/track/1", "https://example.com", "https://example.com/track/1"),
        ("http://other.com/song", "https://base.com", "http://other.com/song"),
        ("/track/123", "https://site.com/music", "https://site.com/track/123"),
        ("track/456", "https://site.com", "https://site.com/track/456"),
        ("/path/to/song", "http://base.com/page/", "http://base.com/path/to/song"),
    ],
)
def test_validate_and_return_absolute_url(sound_url, base_url, expected):
    assert validate_and_return_absolute_url(sound_url, base_url) == expected


@pytest.mark.parametrize(
    ("sound_url", "base_url"),
    [
        ("/track", "ftp://bad.com"),
        ("relative", "not-a-url"),
        ("/x", ""),
    ],
)
def test_validate_and_return_absolute_url_invalid_base(sound_url, base_url):
    with pytest.raises(ValueError, match="Базовый url должен быть абсолютным"):
        validate_and_return_absolute_url(sound_url, base_url)
