import re
import unicodedata


def sanitize_filename(s: str) -> str:
    # NFC: different Unicode representations of the same string (e.g. from macOS vs Linux)
    # must produce the same filename.
    s = unicodedata.normalize("NFC", s)
    # Strip Obsidian hashtags (space + #<letter>...): "Title #tag" → "Title",
    # but "Harry Potter #1" is preserved.
    s = re.sub(r'\s+#[A-Za-z_]\S*.*$', '', s)
    s = re.sub(r'[\x00-\x1f\x7f]', '', s)
    s = re.sub(r'[|/\\:*?"<>]', ' - ', s)
    s = re.sub(r'(\s*-\s*){2,}', ' - ', s)
    s = re.sub(r'\s+', ' ', s)
    result = s.strip(' -.\t')
    return result if result else "Untitled"
