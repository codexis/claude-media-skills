import json
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import youtube_export


# ── extract_video_id ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("url,expected", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),  # bare ID
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s", "dQw4w9WgXcQ"),
])
def test_extract_video_id_valid(url, expected):
    assert youtube_export.extract_video_id(url) == expected


@pytest.mark.parametrize("bad_input", [
    "https://example.com/watch?v=abc",
    "not-a-url",
    "short",
    "",
])
def test_extract_video_id_invalid_raises(bad_input):
    with pytest.raises(ValueError):
        youtube_export.extract_video_id(bad_input)


# ── parse_vtt ─────────────────────────────────────────────────────────────────

def test_parse_vtt_strips_header():
    vtt = textwrap.dedent("""\
        WEBVTT
        Kind: captions
        Language: en

        00:00:01.000 --> 00:00:03.000
        Hello world
    """)
    assert youtube_export.parse_vtt(vtt) == "Hello world"


def test_parse_vtt_deduplicates_adjacent_lines():
    vtt = textwrap.dedent("""\
        WEBVTT

        00:00:01.000 --> 00:00:02.000
        Line one

        00:00:02.000 --> 00:00:03.000
        Line one

        00:00:03.000 --> 00:00:04.000
        Line two
    """)
    assert youtube_export.parse_vtt(vtt) == "Line one Line two"


def test_parse_vtt_preserves_non_adjacent_repeats():
    vtt = textwrap.dedent("""\
        WEBVTT

        00:00:01.000 --> 00:00:02.000
        Repeat

        00:00:02.000 --> 00:00:03.000
        Middle

        00:00:03.000 --> 00:00:04.000
        Repeat
    """)
    assert youtube_export.parse_vtt(vtt) == "Repeat Middle Repeat"


def test_parse_vtt_strips_inline_tags():
    vtt = textwrap.dedent("""\
        WEBVTT

        00:00:01.000 --> 00:00:02.000
        <c.color>Hello</c> <00:00:01.500><c>world</c>
    """)
    assert youtube_export.parse_vtt(vtt) == "Hello world"


def test_parse_vtt_skips_NOTE_lines():
    vtt = textwrap.dedent("""\
        WEBVTT
        NOTE some comment

        00:00:01.000 --> 00:00:02.000
        Content
    """)
    assert youtube_export.parse_vtt(vtt) == "Content"


def test_parse_vtt_empty_input():
    assert youtube_export.parse_vtt("") == ""


# ── _extract_handle ───────────────────────────────────────────────────────────

def test_extract_handle_with_at_prefix():
    assert youtube_export._extract_handle("@mychannel", "") == "@mychannel"


def test_extract_handle_without_at_prefix():
    assert youtube_export._extract_handle("mychannel", "") == "@mychannel"


def test_extract_handle_from_url():
    assert youtube_export._extract_handle("", "https://youtube.com/@mychannel") == "@mychannel"


def test_extract_handle_both_empty():
    assert youtube_export._extract_handle("", "") == ""


def test_extract_handle_prefers_uploader_id_over_url():
    assert youtube_export._extract_handle("fromid", "https://youtube.com/@fromurl") == "@fromid"


# ── get_video_metadata (mocked subprocess) ────────────────────────────────────

def _ytdlp_video_data(**overrides):
    base = {
        "title": "Great Talk",
        "channel": "Smart Channel",
        "channel_url": "https://youtube.com/@smart",
        "uploader_id": "@smart",
        "uploader_url": "https://youtube.com/@smart",
        "upload_date": "20230815",
        "duration": 1800,
    }
    base.update(overrides)
    return base


def test_get_video_metadata_happy_path():
    with patch.object(youtube_export, "_run_ytdlp_json", return_value=_ytdlp_video_data()):
        meta = youtube_export.get_video_metadata("dQw4w9WgXcQ")

    assert meta["title"] == "Great Talk"
    assert meta["upload_date"] == "2023-08-15"
    assert meta["duration_sec"] == 1800
    assert meta["channel_handle"] == "@smart"


def test_get_video_metadata_formats_date():
    with patch.object(youtube_export, "_run_ytdlp_json", return_value=_ytdlp_video_data(upload_date="20010101")):
        meta = youtube_export.get_video_metadata("x")
    assert meta["upload_date"] == "2001-01-01"


def test_get_video_metadata_missing_date():
    with patch.object(youtube_export, "_run_ytdlp_json", return_value=_ytdlp_video_data(upload_date="")):
        meta = youtube_export.get_video_metadata("x")
    assert meta["upload_date"] == ""


def test_get_video_metadata_ytdlp_failure_returns_empty():
    with patch.object(youtube_export, "_run_ytdlp_json", return_value=None):
        meta = youtube_export.get_video_metadata("x")
    assert meta["title"] == "Unknown"
    assert meta["duration_sec"] == 0


# ── get_channel_metadata (cache + subprocess) ─────────────────────────────────

def _ytdlp_channel_data(**overrides):
    base = {
        "webpage_url": "https://youtube.com/@smart",
        "channel": "Smart Channel",
        "uploader_id": "@smart",
        "uploader_url": "https://youtube.com/@smart",
        "description": "We talk about smart things.",
    }
    base.update(overrides)
    return base


def test_get_channel_metadata_cache_hit(monkeypatch):
    cached = {"channel_url": "u", "channel_name": "C", "channel_handle": "@c", "channel_description": "d"}
    monkeypatch.setattr(youtube_export.cache, "get", lambda *a, **kw: cached)

    with patch.object(youtube_export, "_run_ytdlp_json") as mock_run:
        result = youtube_export.get_channel_metadata("u")
        mock_run.assert_not_called()

    assert result == cached


def test_get_channel_metadata_cache_miss_fetches_and_stores(monkeypatch):
    monkeypatch.setattr(youtube_export.cache, "get", lambda *a, **kw: None)
    stored = {}
    monkeypatch.setattr(youtube_export.cache, "put", lambda ns, k, v: stored.update(v))

    with patch.object(youtube_export, "_run_ytdlp_json", return_value=_ytdlp_channel_data()):
        result = youtube_export.get_channel_metadata("https://youtube.com/@smart")

    assert result["channel_name"] == "Smart Channel"
    assert result["channel_handle"] == "@smart"
    assert stored["channel_name"] == "Smart Channel"


def test_get_channel_metadata_ytdlp_failure_returns_empty(monkeypatch):
    monkeypatch.setattr(youtube_export.cache, "get", lambda *a, **kw: None)
    monkeypatch.setattr(youtube_export.cache, "put", lambda *a, **kw: None)

    with patch.object(youtube_export, "_run_ytdlp_json", return_value=None):
        result = youtube_export.get_channel_metadata("https://youtube.com/@dead")

    assert result["channel_name"] == "Unknown"