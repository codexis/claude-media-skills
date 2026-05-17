# media-distill

Converts YouTube videos into atomic [Zettelkasten](https://zettelkasten.de/introduction/) notes for [Obsidian](https://obsidian.md). Share a link and Claude fetches the transcript, distills key ideas, and automatically creates linked `Video/`, `Person/`, `Book/`, and `Author/` notes — ready to use without any copy-paste.

---

## What it does

1. **Fetches** transcript and metadata (title, channel, upload date) via `youtube-transcript-api` with `yt-dlp` as fallback.
2. **Creates a Person note** for the channel (once, skips if already exists).
3. **Creates a Video note** with distilled key ideas in the transcript's language.
4. **Looks up books** mentioned in the video via Google Books / Open Library and creates linked `Book/` and `Author/` notes automatically.
5. **Rewrites wikilinks** to Obsidian pipe syntax (`[[Slow Productivity|Медленная продуктивность]]`) so cross-language links navigate correctly.

---

## Prerequisites

- Python 3.9+
- A `.venv` virtual environment at your Obsidian vault root
- An Obsidian vault — the skill writes files relative to your vault root

---

## Installation

### 1. Install the plugin

Run from your **Obsidian vault root**:

```bash
claude plugin install https://github.com/codexis/claude-media-skills/plugins/media-distill
```

Or from a local clone:

```bash
claude plugin install /path/to/claude-media-skills/plugins/media-distill
```

### 2. Install Python dependencies

Run from your **vault root**:

```bash
python3 -m venv .venv
.venv/bin/pip install -r .claude/skills/media-distill/scripts/requirements.txt
```

### 3. Configure environment (optional but recommended)

```bash
cp .claude/skills/media-distill/scripts/.env.example \
   .claude/skills/media-distill/scripts/.env
```

Edit `.claude/skills/media-distill/scripts/.env` and add your Google Books API key to improve book search quality:

```env
GOOGLE_BOOKS_API_KEY=your_key_here
```

Get a free key at [Google Cloud Console](https://console.cloud.google.com/apis/library/books.googleapis.com). Without a key, the skill falls back to Open Library — most books are still found.

---

## Usage

Send Claude a YouTube URL with an optional command prefix:

| Command                | Meaning                    | Note type         |
|------------------------|----------------------------|-------------------|
| `w <url>` or `s <url>` | Watched / Save             | Full distillation |
| `b <url>`              | Bookmark / Watch later     | Full distillation |
| `a <url>`              | Archive / Source reference | Minimal stub      |

You can also use natural language — Claude infers the status:

```
save this https://youtu.be/abc123
make a note from this video: https://youtu.be/abc123
в закладки https://youtu.be/abc123
```

**Multiple URLs** in one message are processed sequentially.

---

## Output structure

Files are created relative to your Obsidian vault root:

```
Video/
  <video title>.md        ← distilled note
Person/
  <channel name>.md       ← channel stub (created once)
Book/
  <book title>.md         ← book note (English canonical title)
Author/
  <author name>.md        ← author stub
```

---

## Configuration

### Language preference

By default the transcript is fetched preferring `ru` then `en`. To change this, ask Claude to run the script with `--lang`:

```bash
.venv/bin/python3 .claude/skills/media-distill/scripts/youtube_export.py <url> --lang en,ru
```

Note language is always preserved — if the transcript is in Russian, the Video note is written in Russian.

### Channel metadata cache

Channel info is cached in `.claude/skills/media-distill/scripts/.cache/cache.sqlite` with a 30-day TTL. Delete the file to force a refresh.

---

## Troubleshooting

| Error                         | Cause                              | Fix                                      |
|-------------------------------|------------------------------------|------------------------------------------|
| `403 Forbidden`               | YouTube blocking the IP            | Run locally, not in cloud/CI             |
| `TranscriptsDisabled`         | Author disabled captions           | Transcript unavailable — nothing to do   |
| `NoTranscriptFound`           | No captions for requested language | Claude will retry with `--lang en`       |
| Empty transcript              | Private video or no captions       | Check video availability                 |
| `Sign in to confirm your age` | Age-restricted video               | Script does not bypass auth              |
| Book not found                | Not in Google Books / Open Library | A stub note is created; fill in manually |

Playlists (`?list=...`) are not supported — share a specific video URL instead. Shorts and live recordings (with captions) work as regular videos.
