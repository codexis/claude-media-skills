#!/usr/bin/env python3
"""
book_lookup.py — fetches book metadata from Google Books and Open Library, prints JSON to stdout.

Usage:
    python .claude/skills/media-distill/scripts/book_lookup.py --title "Book Title" [--author "Author Name"]

Dependencies:
    pip install -r .claude/skills/media-distill/scripts/requirements.txt

Output (stdout):
    {"title": "...", "authors": ["..."], "year_published": 2005,
     "year_created": null, "pages": 320, "category": "..."}

On error — message to stderr, exit code 1.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from utils import sanitize_filename

try:
    import requests
except ImportError:
    print("requests is not installed. Run: pip install requests", file=sys.stderr)
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

_GOOGLE_BOOKS_API_KEY = os.getenv("GOOGLE_BOOKS_API_KEY")

_OPEN_LIBRARY_UA = "exported-data-skill/0.1 (https://github.com/; personal-obsidian-vault)"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Book metadata lookup")
    parser.add_argument("--title", required=True, help="Book title")
    parser.add_argument("--author", default="", help="Author name (optional)")
    return parser.parse_args()


_BAD_SUBJECT_EXACT = {
    "accessible book",
    "protected daisy",
    "in library",
    "internet archive wishlist",
    "large type books",
    "lending library",
    "open library staff picks",
}

_BAD_SUBJECT_PREFIXES = ("nyt:",)


def _clean_subject(subject: str) -> str | None:
    s = (subject or "").strip()
    if not s:
        return None
    low = s.casefold()
    if low in _BAD_SUBJECT_EXACT:
        return None
    if any(low.startswith(p) for p in _BAD_SUBJECT_PREFIXES):
        return None
    return s


def _pick_subject(subjects: list[str]) -> str | None:
    for s in subjects or []:
        cleaned = _clean_subject(s)
        if cleaned:
            return cleaned
    return None


def _match_author(candidates: list[str], author: str) -> bool:
    if not author:
        return True
    tokens = [t for t in author.casefold().split() if t]
    if not tokens:
        return True
    for c in candidates:
        c_low = (c or "").casefold()
        if all(t in c_low for t in tokens):
            return True
    return False


def fetch_google_books(title: str, author: str) -> dict | None:
    query = f"intitle:{title}"
    if author:
        query += f" inauthor:{author}"
    try:
        params: dict = {"q": query, "maxResults": 5}
        if _GOOGLE_BOOKS_API_KEY:
            params["key"] = _GOOGLE_BOOKS_API_KEY
        resp = requests.get(
            "https://www.googleapis.com/books/v1/volumes",
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"  Google Books unavailable: {e}", file=sys.stderr)
        return None

    items = data.get("items") or []
    if not items:
        return None

    chosen = next(
        (it for it in items if _match_author(it.get("volumeInfo", {}).get("authors", []), author)),
        items[0],
    )
    info = chosen.get("volumeInfo", {})
    raw_date = info.get("publishedDate", "")
    year = int(raw_date[:4]) if raw_date[:4].isdigit() else None
    pages = info.get("pageCount")
    categories = info.get("categories", [])
    return {
        "title": info.get("title"),
        "authors": info.get("authors", []),
        "year_published": year,
        "year_created": None,
        "pages": int(pages) if pages else None,
        "category": _pick_subject(categories),
    }


def fetch_open_library(title: str, author: str) -> dict | None:
    params: dict = {"title": title, "limit": 5}
    if author:
        params["author"] = author
    try:
        resp = requests.get(
            "https://openlibrary.org/search.json",
            params=params,
            headers={"User-Agent": _OPEN_LIBRARY_UA},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"  Open Library unavailable: {e}", file=sys.stderr)
        return None

    docs = data.get("docs") or []
    if not docs:
        return None

    doc = next(
        (d for d in docs if _match_author(d.get("author_name", []), author)),
        docs[0],
    )
    year = doc.get("first_publish_year")
    pages = doc.get("number_of_pages_median")
    subjects = doc.get("subject", [])
    return {
        "title": doc.get("title"),
        "authors": doc.get("author_name", []),
        "year_published": int(year) if year else None,
        "year_created": None,
        "pages": int(pages) if pages else None,
        "category": _pick_subject(subjects),
    }


def merge_results(gb: dict | None, ol: dict | None) -> dict | None:
    primary = gb or ol
    if primary is None:
        return None
    secondary = ol if gb else None

    def pick(field):
        v = primary.get(field)
        if v:
            return v
        return secondary.get(field) if secondary else None

    # Open Library first_publish_year is the original publication year (e.g. 1990 for Fifth Discipline),
    # while Google Books gives the edition year (may be 2020). Prefer OL.
    year_published = (ol.get("year_published") if ol else None) or pick("year_published")

    authors = pick("authors") or []
    unique_authors = list(dict.fromkeys(authors))
    return {
        "title": pick("title"),
        "authors": unique_authors,
        "year_published": year_published,
        "year_created": pick("year_created"),
        "pages": pick("pages"),
        "category": pick("category"),
    }


def main():
    args = parse_args()
    gb = fetch_google_books(args.title, args.author)
    ol = fetch_open_library(args.title, args.author)
    result = merge_results(gb, ol)
    if result is None:
        print(f"Book not found: {args.title!r}", file=sys.stderr)
        sys.exit(1)
    result["safe_title"] = sanitize_filename(result.get("title") or "")
    result["safe_authors"] = [sanitize_filename(a) for a in result.get("authors") or []]
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
