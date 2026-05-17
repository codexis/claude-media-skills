import json
from unittest.mock import MagicMock, patch
import pytest
import book_lookup


# ── _clean_subject ────────────────────────────────────────────────────────────

def test_clean_subject_returns_good_subject():
    assert book_lookup._clean_subject("Business") == "Business"


def test_clean_subject_strips_exact_bad():
    assert book_lookup._clean_subject("Accessible Book") is None


def test_clean_subject_strips_bad_prefix():
    assert book_lookup._clean_subject("nyt:bestseller") is None


def test_clean_subject_empty_returns_none():
    assert book_lookup._clean_subject("") is None


def test_clean_subject_whitespace_only_returns_none():
    assert book_lookup._clean_subject("   ") is None


def test_clean_subject_case_insensitive():
    assert book_lookup._clean_subject("LENDING LIBRARY") is None


# ── _pick_subject ─────────────────────────────────────────────────────────────

def test_pick_subject_returns_first_clean():
    assert book_lookup._pick_subject(["lending library", "Science"]) == "Science"


def test_pick_subject_all_bad_returns_none():
    assert book_lookup._pick_subject(["accessible book", "in library"]) is None


def test_pick_subject_empty_list_returns_none():
    assert book_lookup._pick_subject([]) is None


def test_pick_subject_none_list_returns_none():
    assert book_lookup._pick_subject(None) is None


# ── _match_author ─────────────────────────────────────────────────────────────

def test_match_author_empty_author_always_true():
    assert book_lookup._match_author(["Anyone"], "") is True


def test_match_author_matching_tokens():
    assert book_lookup._match_author(["Peter Drucker"], "Drucker") is True


def test_match_author_full_name_match():
    assert book_lookup._match_author(["Peter F. Drucker"], "Peter Drucker") is True


def test_match_author_case_insensitive():
    assert book_lookup._match_author(["peter drucker"], "PETER DRUCKER") is True


def test_match_author_no_match():
    assert book_lookup._match_author(["Jane Austen"], "Drucker") is False


def test_match_author_empty_candidates():
    assert book_lookup._match_author([], "Drucker") is False


# ── merge_results ─────────────────────────────────────────────────────────────

def test_merge_results_both_none_returns_none():
    assert book_lookup.merge_results(None, None) is None


def test_merge_results_only_gb():
    gb = {"title": "T", "authors": ["A"], "year_published": 2000,
          "year_created": None, "pages": 300, "category": "C"}
    result = book_lookup.merge_results(gb, None)
    assert result["title"] == "T"
    assert result["year_published"] == 2000


def test_merge_results_only_ol():
    ol = {"title": "T", "authors": ["A"], "year_published": 1990,
          "year_created": None, "pages": 250, "category": "D"}
    result = book_lookup.merge_results(None, ol)
    assert result["title"] == "T"
    assert result["year_published"] == 1990


def test_merge_results_prefers_ol_year():
    gb = {"title": "T", "authors": ["A"], "year_published": 2020,
          "year_created": None, "pages": 300, "category": "C"}
    ol = {"title": "T2", "authors": ["A"], "year_published": 1990,
          "year_created": None, "pages": None, "category": None}
    result = book_lookup.merge_results(gb, ol)
    # OL year_published preferred over GB
    assert result["year_published"] == 1990


def test_merge_results_fills_missing_from_secondary():
    gb = {"title": "T", "authors": ["A"], "year_published": 2020,
          "year_created": None, "pages": None, "category": None}
    ol = {"title": "T2", "authors": ["A"], "year_published": 1990,
          "year_created": None, "pages": 400, "category": "Science"}
    result = book_lookup.merge_results(gb, ol)
    assert result["pages"] == 400
    assert result["category"] == "Science"


def test_merge_results_deduplicates_authors():
    gb = {"title": "T", "authors": ["A", "B"], "year_published": 2020,
          "year_created": None, "pages": None, "category": None}
    ol = {"title": "T", "authors": ["A", "B"], "year_published": None,
          "year_created": None, "pages": None, "category": None}
    result = book_lookup.merge_results(gb, ol)
    assert result["authors"] == ["A", "B"]


# ── fetch_google_books (mocked HTTP) ─────────────────────────────────────────

def _gb_response(title="The Goal", authors=("Eliyahu Goldratt",),
                 date="1984-01-01", pages=362, categories=("Business",)):
    return {
        "items": [{
            "volumeInfo": {
                "title": title,
                "authors": list(authors),
                "publishedDate": date,
                "pageCount": pages,
                "categories": list(categories),
            }
        }]
    }


def test_fetch_google_books_happy_path():
    mock_resp = MagicMock()
    mock_resp.json.return_value = _gb_response()
    mock_resp.raise_for_status = MagicMock()

    with patch("book_lookup.requests.get", return_value=mock_resp):
        result = book_lookup.fetch_google_books("The Goal", "Goldratt")

    assert result["title"] == "The Goal"
    assert result["year_published"] == 1984
    assert result["pages"] == 362
    assert result["category"] == "Business"


def test_fetch_google_books_no_items_returns_none():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"items": []}
    mock_resp.raise_for_status = MagicMock()

    with patch("book_lookup.requests.get", return_value=mock_resp):
        assert book_lookup.fetch_google_books("Unknown", "") is None


def test_fetch_google_books_network_error_returns_none():
    import requests as req
    with patch("book_lookup.requests.get", side_effect=req.RequestException("timeout")):
        assert book_lookup.fetch_google_books("T", "") is None


def test_fetch_google_books_invalid_date():
    mock_resp = MagicMock()
    mock_resp.json.return_value = _gb_response(date="unknown")
    mock_resp.raise_for_status = MagicMock()

    with patch("book_lookup.requests.get", return_value=mock_resp):
        result = book_lookup.fetch_google_books("T", "")
    assert result["year_published"] is None


# ── fetch_open_library (mocked HTTP) ─────────────────────────────────────────

def _ol_response(title="The Goal", authors=("Eliyahu Goldratt",),
                 year=1984, pages=362, subjects=("Business",)):
    return {
        "docs": [{
            "title": title,
            "author_name": list(authors),
            "first_publish_year": year,
            "number_of_pages_median": pages,
            "subject": list(subjects),
        }]
    }


def test_fetch_open_library_happy_path():
    mock_resp = MagicMock()
    mock_resp.json.return_value = _ol_response()
    mock_resp.raise_for_status = MagicMock()

    with patch("book_lookup.requests.get", return_value=mock_resp):
        result = book_lookup.fetch_open_library("The Goal", "Goldratt")

    assert result["title"] == "The Goal"
    assert result["year_published"] == 1984
    assert result["pages"] == 362


def test_fetch_open_library_empty_docs_returns_none():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"docs": []}
    mock_resp.raise_for_status = MagicMock()

    with patch("book_lookup.requests.get", return_value=mock_resp):
        assert book_lookup.fetch_open_library("Unknown", "") is None


def test_fetch_open_library_network_error_returns_none():
    import requests as req
    with patch("book_lookup.requests.get", side_effect=req.RequestException("timeout")):
        assert book_lookup.fetch_open_library("T", "") is None