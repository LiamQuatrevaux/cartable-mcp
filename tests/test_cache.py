import ecoledirecte_mcp.cache as cache_module
from ecoledirecte_mcp.cache import TTLCache


def test_set_then_get_returns_value():
    cache = TTLCache(default_ttl=60)
    cache.set("a", {"value": 1})

    assert cache.get("a") == {"value": 1}
    assert cache.stats()["hits"] == 1


def test_expired_entries_are_dropped(monkeypatch):
    now = 1000.0
    monkeypatch.setattr(cache_module.time, "monotonic", lambda: now)
    cache = TTLCache()
    cache.set("a", 1, ttl=10)

    now = 1011.0
    assert cache.get("a") is None
    assert cache.stats()["entries"] == 0


def test_cache_is_bounded(monkeypatch):
    monkeypatch.setattr(cache_module.time, "monotonic", lambda: 1.0)
    cache = TTLCache(max_entries=2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)

    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3


def test_clear_with_prefix():
    cache = TTLCache()
    cache.set("notes|1", 1)
    cache.set("notes|2", 2)
    cache.set("messages|1", 3)

    cache.clear("notes|")

    assert cache.get("notes|1") is None
    assert cache.get("messages|1") == 3
