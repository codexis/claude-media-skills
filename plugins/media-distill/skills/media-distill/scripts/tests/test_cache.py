import time
import pytest
import cache


@pytest.fixture(autouse=True)
def tmp_cache(tmp_path, monkeypatch):
    """Redirect cache storage to a temp directory for each test."""
    monkeypatch.setattr(cache, "_CACHE_DIR", tmp_path / ".cache")
    monkeypatch.setattr(cache, "_CACHE_PATH", tmp_path / ".cache" / "cache.sqlite")


def test_get_missing_key_returns_none():
    assert cache.get("ns", "no-such-key") is None


def test_put_then_get_returns_data():
    cache.put("ns", "k", {"x": 1})
    assert cache.get("ns", "k") == {"x": 1}


def test_different_namespaces_are_isolated():
    cache.put("ns1", "k", {"a": 1})
    cache.put("ns2", "k", {"b": 2})
    assert cache.get("ns1", "k") == {"a": 1}
    assert cache.get("ns2", "k") == {"b": 2}


def test_put_overwrites_existing():
    cache.put("ns", "k", {"v": 1})
    cache.put("ns", "k", {"v": 2})
    assert cache.get("ns", "k") == {"v": 2}


def test_expired_entry_returns_none(monkeypatch):
    cache.put("ns", "k", {"data": "old"})
    # TTL of 0 seconds — everything is expired immediately
    assert cache.get("ns", "k", ttl_sec=0) is None


def test_within_ttl_returns_data():
    cache.put("ns", "k", {"data": "fresh"})
    assert cache.get("ns", "k", ttl_sec=9999) == {"data": "fresh"}


def test_unicode_values_survive_round_trip():
    payload = {"text": "Привет мир 日本語"}
    cache.put("ns", "unicode", payload)
    assert cache.get("ns", "unicode") == payload


def test_nested_dict_survives_round_trip():
    payload = {"a": {"b": [1, 2, 3]}}
    cache.put("ns", "nested", payload)
    assert cache.get("ns", "nested") == payload


def test_get_after_ttl_boundary(monkeypatch):
    """Entry fetched just before TTL expiry must still be returned."""
    cache.put("ns", "k", {"v": "ok"})
    # Mock time to be just under TTL
    original = time.time()
    monkeypatch.setattr(time, "time", lambda: original + 99)
    assert cache.get("ns", "k", ttl_sec=100) == {"v": "ok"}


def test_get_after_ttl_exceeded(monkeypatch):
    cache.put("ns", "k", {"v": "ok"})
    original = time.time()
    monkeypatch.setattr(time, "time", lambda: original + 101)
    assert cache.get("ns", "k", ttl_sec=100) is None