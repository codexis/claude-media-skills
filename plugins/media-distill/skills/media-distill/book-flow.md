# Book recommendations flow

Invoked from `SKILL.md` step 5 for each forward `[[...]]` wikilink in the Video note that points to a book or a book's author.

**Input:** `tentative_title` (the exact string inside the wikilink from the Video — usually in the source language, e.g. `Медленная продуктивность`), optionally a `tentative_author` if an author was mentioned alongside the book.

**Output:** Book and Author notes under canonical filenames (`safe_title` / `safe_authors[i]` from `book_lookup.py`, usually English); Video wikilinks rewritten to Obsidian pipe syntax `[[canonical|tentative]]` so the link navigates to the canonical file while preserving source-language display. `aliases:` field on the Book/Author note mirrors the tentative name — useful for Obsidian quick-switcher and search, though Obsidian does not use `aliases:` to resolve `[[alias]]` wikilinks automatically.

## 1. Find the book metadata

```bash
.venv/bin/python3 .claude/skills/media-distill/scripts/book_lookup.py --title "<tentative_title>" [--author "<tentative_author>"]
```

The script queries Google Books and Open Library, prints JSON to stdout:
```json
{
  "title": "The Fifth Discipline",
  "authors": ["Peter M. Senge"],
  "year_published": 1990,
  "year_created": null,
  "pages": 423,
  "category": "Business & Economics",
  "safe_title": "The Fifth Discipline",
  "safe_authors": ["Peter M. Senge"]
}
```

If the book is **not found** (exit code 1) — go to §4 «Book not found» below.

## 2. Create the Author note (Author/)

For each author in the `safe_authors` field of the JSON:

- Check whether `Author/<safe_authors[i]>.md` exists.
- **If missing** — create the file from `.claude/skills/media-distill/templates/author.md`, substituting the author name from `authors[]` (original, for display).
- **If exists** — keep the existing file. Only update `aliases:` as described below.
- With several authors — create a note for each.

**Aliases.** If `tentative_author` was provided from the Video and `safe_authors[i] != tentative_author` (after trimming / case-insensitive compare), add `tentative_author` to the `aliases:` list of the Author note. If the alias is already present, do nothing. Example: Video has `[[Кэл Ньюпорт]]`, `safe_authors` is `["Cal Newport"]` → `Author/Cal Newport.md` gets `aliases: - "Кэл Ньюпорт"`. Obsidian then resolves `[[Кэл Ньюпорт]]` to the canonical file.

## 3. Create the Book note (Book/)

Check whether `Book/<safe_title>.md` exists:

- **If it exists** — do not overwrite, do not ask the user via `AskUserQuestion`. Update the existing note in place:
  - Append the current video to `sources:` (if not already listed).
  - Append the current channel to `recommended_by:` (if not already listed).
  - If `tentative_title` differs from `safe_title` and is not already in `aliases:` — append it.
- **If missing** — create it from `.claude/skills/media-distill/templates/book.md`, substituting:

| Template field | Source |
|---|---|
| `{{title}}` | `title` from JSON |
| `{{author_name}}` | each element of `safe_authors[]` as a separate `- "[[...]]"` line (see "List fields" below) |
| `{{book_category}}` | `category` from JSON (see "Null fields" below; if `null` — drop the wikilink wrapper) |
| `{{year_created}}` | `year_created` from JSON (empty if null) |
| `{{year_published}}` | `year_published` from JSON (empty if null) |
| `{{book_pages_count}}` | `pages` from JSON (empty if null) |
| `{{channel_name}}` | `safe_channel_name` from the youtube_export JSON (who recommended); if the recommendation is not from YouTube — clear the `recommended_by` field |
| `{{video_title}}` | `safe_title` from the youtube_export JSON (so the wikilink connects to the `Video/` file); if not from YouTube — clear the `sources` field |

**Aliases.** If `tentative_title` was provided from the Video and `safe_title != tentative_title` (after trimming / case-insensitive compare), add `tentative_title` to the `aliases:` list of the Book note. If they match — leave `aliases:` empty. Example: Video has `[[Медленная продуктивность]]`, `safe_title` is `Slow Productivity` → `Book/Slow Productivity.md` gets `aliases: - "Медленная продуктивность"`.

## 4. Book not found

If `book_lookup.py` exited 1 (no metadata found):

- Create `Book/<tentative_title>.md` from the template. Leave `category`, `year_created`, `year_published`, `pages_total` empty (see «Null fields» below).
- `authors:` — fill with `[[<tentative_author>]]` if the author is known from the Video, otherwise leave empty.
- `recommended_by:` — `[[<safe_channel_name>]]` (from the youtube_export JSON).
- `sources:` — `[[<video safe_title>]]`.
- `aliases:` — leave empty (the filename itself matches the Video wikilink).
- If `tentative_author` is known, also create `Author/<tentative_author>.md` from the author template as a bare stub.
- Do not treat this as an error — the stub can be filled in manually later.
- Since the Book filename already equals `tentative_title`, no wikilink rewrite in the Video is needed (see §5). The Author case is symmetric.

## 5. Rewrite Video wikilinks to pipe syntax

After §2 and §3 have produced the canonical Book/Author filenames, update each matching wikilink in the Video note to Obsidian pipe syntax — **this is the only Video-editing step in the flow**:

| Before (Video) | After (Video) |
|---|---|
| `[[Медленная продуктивность]]` | `[[Slow Productivity\|Медленная продуктивность]]` |
| `[[Кэл Ньюпорт]]` | `[[Cal Newport\|Кэл Ньюпорт]]` |

Rule: rewrite only when `canonical != tentative`. If they match, leave the wikilink as is. **Why needed:** Obsidian does not resolve `[[alias]]` through the `aliases:` frontmatter field — only the pipe syntax navigates to the canonical file while displaying the source-language name.

Do not touch wikilinks that were not processed by this flow (e.g. `[[concept]]` references inside a distillation body).

## List fields (YAML arrays)

Several `book.md` frontmatter fields are YAML arrays. Fill them with **one or more lines**, one item per line. Never use inline arrays (`[...]`).

| Field | When to use multiple lines |
|---|---|
| `authors` | if the book has several authors |
| `recommended_by` | if recommended by several sources |
| `sources` | if the book appears in multiple videos/articles |

**Single item:**
```yaml
authors:
  - "[[Peter M. Senge]]"
```

**Multiple items:**
```yaml
authors:
  - "[[James Clear]]"
  - "[[B. J. Fogg]]"
recommended_by:
  - "[[Channel One]]"
  - "[[Channel Two]]"
```

The template contains a single placeholder line (`- "[[{{author_name}}]]"` etc.) — that's standard YAML, not a limit of one value. Add as many lines as needed when substituting.

## Null fields

Fields in the `book_lookup.py` JSON that can be `null`: `category`, `year_created`, `year_published`, `pages`.

For such fields **drop the wikilink wrapper entirely** and leave the key with no value:

| JSON | Frontmatter (null) | Frontmatter (value) |
|---|---|---|
| `category: null` | `category:` | `category: "[[Business & Economics]]"` |
| `year_created: null` | `year_created:` | `year_created: 1990` |
| `year_published: null` | `year_published:` | `year_published: 2006` |
| `pages: null` | `pages_total:` | `pages_total: 423` |

Never write `category: "[[]]"` — that's a broken wikilink.
