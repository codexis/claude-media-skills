---
name: media-distill
description: "Fetches a YouTube video transcript and creates a zettelkasten note. Use when the user shares a YouTube link and asks to save / summarize / take a note (also works with short commands `w/s/b/a <url>`). Triggers on phrases like 'save this', 'make a note', 'сохрани это', 'сделай заметку', 'в закладки', 'summary', 'конспект'."
---

# YouTube → Zettelkasten

Turns a YouTube video into an atomic Zettelkasten note and stores it under `Video/`.

## When to use

- User sends a YouTube URL and asks for a summary / note / recap.
- User says "save this", "make a note", "сохрани это", "сделай заметку" about a video.
- You need to distill knowledge from a lecture, podcast, or tutorial.

## Determining status from the user's command

Status is derived from the meaning of the message or from a short command prefix before the link.

| Command              | Synonyms / intent                                 | status       |
|----------------------|---------------------------------------------------|--------------|
| `w <url>`, `s <url>` | "save", "make a note", "watched", «сохрани»       | `watched`    |
| `b <url>`            | "bookmark", "watch later", «в закладки»           | `bookmarked` |
| `a <url>`            | "archive", "source", "mentioned", «в архив»       | `archived`   |

If no command prefix is given — infer from the phrasing. Default: `watched`.

## Dependencies

```bash
pip install -r .claude/skills/media-distill/scripts/requirements.txt
```

## Handling multiple URLs

If the user's message contains several YouTube URLs — process each one sequentially, creating a separate note per URL using the process below. Report intermediate progress to the user.

## Playlists, shorts, live

- **Shorts** (`/shorts/<id>`) — treated as regular videos.
- **Playlists** (`?list=...`) — not supported. Ask the user for a specific video URL from the playlist.
- **Live recording** — treated as a regular video if subtitles are available. For an active live stream the transcript is usually unavailable.

## Process (step by step)

### 1. Fetch transcript and metadata

```bash
.venv/bin/python3 .claude/skills/media-distill/scripts/youtube_export.py <URL> [--lang ru,en]
```

The script prints JSON to stdout:
```json
{
  "video_id": "abc123",
  "url": "https://www.youtube.com/watch?v=abc123",
  "transcript": "full text...",
  "lang": "ru",
  "title": "Video title",
  "channel": "Channel name",
  "upload_date": "2024-03-15",
  "duration_sec": 1080,
  "channel_url": "https://www.youtube.com/channel/UC...",
  "channel_name": "Channel name",
  "channel_handle": "@handle",
  "channel_description": "Channel description...",
  "safe_title": "Video title",
  "safe_channel_name": "Channel name"
}
```

On error — a message in stderr, exit code 1.

**The transcript is not saved** to the vault as a separate file — it is only used to generate the note, then discarded.

Channel metadata is cached in `scripts/.cache/cache.sqlite` (30-day TTL) — repeated videos from the same channel reuse cached data. The cache file is gitignored.

### 2. Check for filename collisions

Before creating `Video/<safe_title>.md`, check whether the file exists.

**If the file exists** — ask the user via `AskUserQuestion`:
- **Skip** — note already exists, do nothing.
- **Overwrite** — recreate the note (manual edits will be lost).
- **Add video_id suffix** — create `Video/<safe_title> (<video_id>).md`.

Same rule applies to `Book/<safe_title>.md`. For `Person/` and `Author/` a collision simply means "file exists" and should not be overwritten (see §3 and §4).

### 3. Check and create the Person note

Use `safe_channel_name` from the JSON as both the filename and the wikilink target.

Check whether `Person/<safe_channel_name>.md` exists:

- **If it exists** — continue, use `[[<safe_channel_name>]]` as the author reference. The Person note is not overwritten (even if `channel_description` has changed).
- **If missing** — create it from `.claude/skills/media-distill/templates/person.md`, substituting fields from the JSON.

**Placeholders in `person.md`:**

| Placeholder | Source (JSON) |
|---|---|
| `{{channel_handle}}` | `channel_handle` (channel handle, `@name` format) |
| `{{channel_url}}` | `channel_url` |
| `{{channel_description}}` | `channel_description` |

### 4. Create the Video note

**Pick the template by status:**

| status | Template |
|---|---|
| `watched` | `.claude/skills/media-distill/templates/video.md` (full distillation) |
| `bookmarked` | `.claude/skills/media-distill/templates/video.md` (full distillation — produce it now, even if the user hasn't watched yet) |
| `archived` | `.claude/skills/media-distill/templates/video-archived.md` (minimal stub) |

**Placeholders (both video.md variants):**

| Placeholder | Source |
|---|---|
| `{{url}}` | `url` from JSON |
| `{{safe_channel_name}}` | `safe_channel_name` from JSON (sanitized — must match the `Person/` filename) |
| `{{upload_date}}` | `upload_date` from JSON (video publish date, `YYYY-MM-DD`) |
| `{{save_date}}` | today's date in `YYYY-MM-DD` |
| `{{status}}` | `watched` / `bookmarked` / `archived` (from user command) |
| `{{duration_sec}}` | `duration_sec` from JSON |
| `{{lang}}` | `lang` from JSON (transcript language) |
| `{{title}}` | `title` from JSON (original title used as the note heading) |

**Filename:** `Video/<safe_title>.md` (field `safe_title` from the JSON).

**Requirements for full-distillation notes (`watched` / `bookmarked`):**
- Note language = transcript language (`lang`). This is the one rule that stays language-of-source regardless of these English instructions.
- Each idea is atomic: one section = one thought.
- No retelling — only distillation of meaning.
- Tags as `#word`, wikilinks as `[[concept]]`.
- Forward-wikilinks on books/authors (`[[Book Title]]`, `[[Author Name]]`) in the body are the trigger for step 5. Write them in the source language as they sound in the video — do not try to guess the canonical English title. Alias resolution happens in step 5.

**Requirements for `archived` notes:**
- 1–2 sentences of context — **why** this note exists as a source (what is referenced, what it links to).
- No "Key ideas", "Practice", "Related" sections — the note is a stub for backlinks.
- If the video is a book review / summary / breakdown, the context sentence naturally contains `[[Book Title]]` and `[[Author Name]]` wikilinks. Write them in the source language; step 5 resolves them.

### 5. Post-process — book/author references

**Trigger:** any forward `[[...]]` wikilink in the Video note body (context sentence for `archived`, body / Related section for `watched` / `bookmarked`) that points to a book or a book's author. If the video is a book review / summary / breakdown / «разбор книги» / «конспект книги», this step is mandatory.

**Action:** for each such wikilink pass through `book-flow.md`, passing the tentative name (exactly as written in the wikilink) as the input. Several books in one video → one pass per book.

**Wikilink rewrite.** After `book-flow.md` finishes and the canonical Book/Author filenames are known, rewrite each matching wikilink in the Video note to Obsidian pipe syntax `[[canonical|tentative]]` — e.g. `[[Медленная продуктивность]]` → `[[Slow Productivity|Медленная продуктивность]]`. Reason: Obsidian does not auto-resolve `[[alias]]` through the `aliases:` frontmatter field inside wikilinks; the pipe form is required for the link to navigate to the canonical file while keeping the source-language display. If `tentative == canonical`, leave the wikilink as is.

## Common errors

| Error | Cause | Resolution |
|--------|---------|---------|
| `403 Forbidden` | YouTube is blocking the IP | Run locally, not in CI/cloud |
| `TranscriptsDisabled` | Author disabled captions | Transcript unavailable |
| `NoTranscriptFound` | No captions for the requested language | Add `--lang en` |
| Empty transcript | Private video or no captions | Check video availability |
| `Sign in to confirm your age` | Age-restricted | Inform the user — the script does not bypass auth |

## Skill files

```
.claude/skills/media-distill/
├── SKILL.md              ← this file (video flow, triggers, common errors)
├── book-flow.md          ← book recommendations flow (templates, list/null fields)
├── templates/
│   ├── person.md         ← template for Person/
│   ├── video.md          ← template for Video/ (watched / bookmarked)
│   ├── video-archived.md ← template for Video/ with status: archived
│   ├── author.md         ← template for Author/
│   └── book.md           ← template for Book/
└── scripts/
    ├── youtube_export.py ← fetches video/channel data
    ├── book_lookup.py    ← looks up book metadata
    ├── cache.py          ← SQLite cache for channel metadata (30-day TTL)
    ├── utils.py          ← sanitize_filename() — shared helper
    ├── requirements.txt  ← dependencies
    └── .cache/           ← cache.sqlite (runtime, gitignored)
```
