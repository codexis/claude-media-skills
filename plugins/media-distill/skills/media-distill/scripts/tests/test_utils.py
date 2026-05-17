import unicodedata
import pytest
from utils import sanitize_filename


def test_basic_string():
    assert sanitize_filename("Hello World") == "Hello World"


def test_strips_obsidian_hashtag():
    assert sanitize_filename("My Book #tag") == "My Book"


def test_strips_multiple_hashtags():
    assert sanitize_filename("My Book #tag #another") == "My Book"


def test_preserves_numbered_suffix():
    # "Harry Potter #1" must NOT be stripped — digit follows #
    assert sanitize_filename("Harry Potter #1") == "Harry Potter #1"


def test_nfc_normalization():
    # é as NFD (e + combining acute) must become NFC é
    nfd = unicodedata.normalize("NFD", "café")
    nfc = unicodedata.normalize("NFC", "café")
    assert sanitize_filename(nfd) == nfc


def test_replaces_pipe():
    assert sanitize_filename("a|b") == "a - b"


def test_replaces_backslash():
    assert sanitize_filename("a\\b") == "a - b"


def test_replaces_slash():
    assert sanitize_filename("a/b") == "a - b"


def test_replaces_colon():
    assert sanitize_filename("a:b") == "a - b"


def test_replaces_asterisk():
    assert sanitize_filename("a*b") == "a - b"


def test_replaces_question_mark():
    assert sanitize_filename("a?b") == "a - b"


def test_replaces_double_quote():
    assert sanitize_filename('a"b') == "a - b"


def test_replaces_angle_brackets():
    assert sanitize_filename("a<b>c") == "a - b - c"


def test_collapses_repeated_dashes():
    assert sanitize_filename("a - - b") == "a - b"


def test_strips_leading_trailing_spaces():
    assert sanitize_filename("  hello  ") == "hello"


def test_strips_leading_trailing_dashes():
    assert sanitize_filename("- hello -") == "hello"


def test_strips_leading_trailing_dots():
    assert sanitize_filename("..hello..") == "hello"


def test_empty_string_returns_untitled():
    assert sanitize_filename("") == "Untitled"


def test_whitespace_only_returns_untitled():
    assert sanitize_filename("   ") == "Untitled"


def test_strips_control_characters():
    # Control chars are deleted (not replaced with space)
    assert sanitize_filename("hello\x00world\x1f") == "helloworld"


def test_collapses_multiple_spaces():
    assert sanitize_filename("a   b") == "a b"


def test_unicode_preserved():
    assert sanitize_filename("Привет мир") == "Привет мир"


def test_complex_title():
    result = sanitize_filename("The 5th Wave: Book #tag #sci-fi")
    assert result == "The 5th Wave - Book"