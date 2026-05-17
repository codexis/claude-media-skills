import re
import unicodedata


def sanitize_filename(s: str) -> str:
    # NFC: разные Unicode-представления одной строки (напр. из macOS vs Linux)
    # должны дать одно имя файла.
    s = unicodedata.normalize("NFC", s)
    # Срезаем Obsidian-хэштеги (пробел + #<буква>...): "Title #tag" → "Title",
    # но "Harry Potter #1" остаётся.
    s = re.sub(r'\s+#[A-Za-z_]\S*.*$', '', s)
    s = re.sub(r'[\x00-\x1f\x7f]', '', s)
    s = re.sub(r'[|/\\:*?"<>]', ' - ', s)
    s = re.sub(r'(\s*-\s*){2,}', ' - ', s)
    s = re.sub(r'\s+', ' ', s)
    result = s.strip(' -.\t')
    return result if result else "Untitled"
