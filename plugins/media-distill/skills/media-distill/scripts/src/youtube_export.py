#!/usr/bin/env python3
"""
youtube_export.py — fetches a YouTube video transcript and metadata, prints JSON to stdout.

Usage:
    python .claude/skills/media-distill/scripts/youtube_export.py <youtube_url_or_video_id> [--lang ru,en]

Dependencies:
    pip install -r .claude/skills/media-distill/scripts/requirements.txt

Output (stdout):
    {"video_id": "...", "transcript": "...", "lang": "ru", "title": "...",
     "channel": "...", "duration_sec": 1080, "url": "...",
     "channel_url": "...", "channel_name": "...", "channel_description": "..."}

On error — message to stderr, exit code 1.
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import (
        CouldNotRetrieveTranscript,
        NoTranscriptFound,
        TranscriptsDisabled,
    )
except ImportError:
    print("youtube-transcript-api is not installed. Run: pip install -r .claude/skills/media-distill/scripts/requirements.txt", file=sys.stderr)
    sys.exit(1)

import cache
from utils import sanitize_filename


def _run_ytdlp_json(cmd: list[str], timeout: int = 120) -> dict | None:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        return json.loads(result.stdout.strip())
    except (json.JSONDecodeError, ValueError):
        return None


def extract_video_id(url: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})", url)
    if m:
        return m.group(1)
    # Bare video ID passed directly (11 chars)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url):
        return url
    raise ValueError(f"Could not extract video_id from: {url}")


def fetch_transcript_api(video_id: str, lang_prefs: list[str]) -> tuple[str, str]:
    api = YouTubeTranscriptApi()
    try:
        transcript_list = api.list(video_id)
        for lang in lang_prefs:
            try:
                t = transcript_list.find_transcript([lang])
                snippets = list(t.fetch())
                return " ".join(s.text if hasattr(s, "text") else s.get("text", "") for s in snippets), lang
            except NoTranscriptFound:
                continue
        # Fall back to the first available language
        try:
            t = next(iter(transcript_list))
        except StopIteration:
            raise RuntimeError("No transcript available in any language.")
        snippets = list(t.fetch())
        return " ".join(s.text if hasattr(s, "text") else s.get("text", "") for s in snippets), t.language_code
    except TranscriptsDisabled:
        raise RuntimeError("Subtitles are disabled for this video.")


def parse_vtt(vtt_text: str) -> str:
    # Rolling-display YouTube autocaps repeat adjacent lines;
    # deduplicate only against the previous line, not globally —
    # to preserve intentional repetition in speech.
    lines = vtt_text.splitlines()
    clean: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        if line.startswith(("WEBVTT", "NOTE", "Kind:", "Language:")):
            continue
        if re.match(r"^\d+$", line.strip()) or "-->" in line:
            continue
        line = re.sub(r"<[^>]+>", "", line).strip()
        if line and (not clean or clean[-1] != line):
            clean.append(line)
    return " ".join(clean)


def fetch_transcript_ytdlp(video_id: str, lang_prefs: list[str], tmp_dir: Path) -> tuple[str, str]:
    url = f"https://www.youtube.com/watch?v={video_id}"
    cmd = [
        "yt-dlp",
        "--skip-download",
        "--write-auto-sub",
        "--write-sub",
        "--sub-langs", ",".join(lang_prefs),
        "--sub-format", "vtt",
        "--output", str(tmp_dir / "%(id)s"),
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp error:\n{result.stderr}")

    vtt_files = list(tmp_dir.glob("*.vtt"))
    if not vtt_files:
        raise RuntimeError("yt-dlp did not download any subtitles. They may be unavailable.")

    by_lang: dict[str, Path] = {}
    for vf in vtt_files:
        # yt-dlp names files as <id>.<lang>.vtt — the second-to-last suffix is the language.
        suffixes = vf.suffixes  # e.g. ['.ru', '.vtt']
        lang = suffixes[-2].lstrip(".") if len(suffixes) >= 2 else "unknown"
        by_lang.setdefault(lang, vf)

    chosen_file: Path | None = None
    chosen_lang = ""
    for pref in lang_prefs:
        for lang, vf in by_lang.items():
            if lang == pref or lang.startswith(f"{pref}-"):
                chosen_file, chosen_lang = vf, lang
                break
        if chosen_file is not None:
            break

    if chosen_file is None:
        chosen_lang, chosen_file = next(iter(by_lang.items()))

    return parse_vtt(chosen_file.read_text(encoding="utf-8")), chosen_lang


def get_transcript(video_id: str, lang_prefs: list[str], tmp_dir: Path) -> tuple[str, str]:
    try:
        print("→ youtube-transcript-api...", file=sys.stderr)
        return fetch_transcript_api(video_id, lang_prefs)
    except (CouldNotRetrieveTranscript, RuntimeError) as e:
        print(f"  error: {e}", file=sys.stderr)
        print("→ fallback: yt-dlp...", file=sys.stderr)
        return fetch_transcript_ytdlp(video_id, lang_prefs, tmp_dir)


def _extract_handle(uploader_id: str, uploader_url: str) -> str:
    if uploader_id:
        return uploader_id if uploader_id.startswith("@") else f"@{uploader_id}"
    if uploader_url and "/@" in uploader_url:
        return "@" + uploader_url.split("/@")[1].split("/")[0]
    return ""


def get_video_metadata(video_id: str) -> dict:
    url = f"https://www.youtube.com/watch?v={video_id}"
    data = _run_ytdlp_json(["yt-dlp", "--skip-download", "--print-json", url])
    empty = {"title": "Unknown", "channel": "Unknown", "channel_url": "", "channel_handle": "", "upload_date": "", "duration_sec": 0}
    if data is None:
        return empty

    handle = _extract_handle(
        data.get("uploader_id", ""),
        data.get("uploader_url", "") or data.get("channel_url", ""),
    )
    raw_date = data.get("upload_date", "")  # YYYYMMDD from yt-dlp
    upload_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}" if len(raw_date) == 8 else ""
    return {
        "title": data.get("title", "Unknown"),
        "channel": data.get("channel") or data.get("uploader", "Unknown"),
        "channel_url": data.get("channel_url") or data.get("uploader_url", ""),
        "channel_handle": handle,
        "upload_date": upload_date,
        "duration_sec": int(data.get("duration") or 0),
    }


def get_channel_metadata(channel_url: str) -> dict:
    cached = cache.get("channel", channel_url)
    if cached is not None:
        print("  (from cache)", file=sys.stderr)
        return cached

    # --playlist-items 0 — skip video list, fetch channel metadata only.
    cmd = ["yt-dlp", "--playlist-items", "0", "--dump-single-json", channel_url]
    data = _run_ytdlp_json(cmd)
    empty = {"channel_url": channel_url, "channel_name": "Unknown", "channel_handle": "", "channel_description": ""}
    if data is None:
        return empty

    handle = _extract_handle(
        data.get("uploader_id", "") or data.get("channel_id", ""),
        data.get("uploader_url", "") or data.get("webpage_url", ""),
    )
    result = {
        "channel_url": data.get("webpage_url") or data.get("url") or channel_url,
        "channel_name": data.get("channel") or data.get("uploader") or data.get("title", "Unknown"),
        "channel_handle": handle,
        "channel_description": data.get("description", ""),
    }
    cache.put("channel", channel_url, result)
    return result


def main():
    parser = argparse.ArgumentParser(description="Fetch a YouTube video transcript and output JSON")
    parser.add_argument("url", help="YouTube URL or video ID")
    parser.add_argument("--lang", default="ru,en", help="Comma-separated subtitle language preferences (default: ru,en)")
    parser.add_argument("--no-meta", action="store_true", help="Skip video metadata fetch")
    parser.add_argument("--no-channel", action="store_true", help="Skip channel metadata fetch")
    args = parser.parse_args()

    lang_prefs = [lang.strip() for lang in args.lang.split(",")]

    try:
        video_id = extract_video_id(args.url)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    with tempfile.TemporaryDirectory(prefix="youtube_export_") as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        try:
            transcript, lang_used = get_transcript(video_id, lang_prefs, tmp_dir)
        except Exception as e:
            print(f"Failed to fetch transcript: {e}", file=sys.stderr)
            sys.exit(1)

    if not transcript.strip():
        print("Transcript is empty.", file=sys.stderr)
        sys.exit(1)

    metadata = {}
    if not args.no_meta:
        print("→ video metadata...", file=sys.stderr)
        try:
            metadata = get_video_metadata(video_id)
        except Exception as e:
            print(f"  metadata unavailable: {e}", file=sys.stderr)

    channel_meta = {}
    if not args.no_channel:
        channel_url = metadata.get("channel_url", "")
        if channel_url:
            print("→ channel metadata...", file=sys.stderr)
            try:
                channel_meta = get_channel_metadata(channel_url)
            except Exception as e:
                print(f"  channel metadata unavailable: {e}", file=sys.stderr)

    handle = (
        channel_meta.get("channel_handle")
        or metadata.get("channel_handle")
        or ""
    )
    result = {
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "transcript": transcript,
        "lang": lang_used,
        "title": metadata.get("title", "Unknown"),
        "channel": metadata.get("channel", "Unknown"),
        "upload_date": metadata.get("upload_date", ""),
        "duration_sec": metadata.get("duration_sec", 0),
        "channel_url": channel_meta.get("channel_url", metadata.get("channel_url", "")),
        "channel_name": channel_meta.get("channel_name", metadata.get("channel", "Unknown")),
        "channel_handle": handle,
        "channel_description": channel_meta.get("channel_description", ""),
        "safe_title": sanitize_filename(metadata.get("title", "Unknown")),
        "safe_channel_name": sanitize_filename(channel_meta.get("channel_name", metadata.get("channel", "Unknown"))),
    }

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
