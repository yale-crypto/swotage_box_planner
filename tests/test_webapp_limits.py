"""
Request-level guards on the packing API: problem-size caps, rate limiting and
the search time budget.

Run with:  pytest tests/ -v
"""

import sys, os, time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from webapp import app as webapp
from binpack import Box, Item, PackingEngine


BOX = {"l": 10, "w": 10, "h": 10}


@pytest.fixture
def client(monkeypatch):
    # A fresh bucket per test: the limiter is process-wide, so tests would
    # otherwise throttle one another.
    monkeypatch.setattr(webapp, "_limiter", webapp._TokenBucket(1000, 6000))
    webapp.app.config.update(TESTING=True)
    return webapp.app.test_client()


def post(client, items, box=BOX):
    return client.post("/api/pack", json={"box": box, "items": items})


class TestProblemSizeCaps:
    def test_quantity_per_type_is_capped(self, client):
        r = post(client, [{"id": "A", "l": 1, "w": 1, "h": 1, "qty": 100000}])
        assert r.status_code == 400
        assert "exceeds the limit" in r.get_json()["error"]

    def test_total_units_are_capped(self, client, monkeypatch):
        monkeypatch.setattr(webapp, "MAX_TOTAL_UNITS", 10)
        r = post(client, [
            {"id": "A", "l": 1, "w": 1, "h": 1, "qty": 6},
            {"id": "B", "l": 1, "w": 1, "h": 1, "qty": 6},
        ])
        assert r.status_code == 400
        assert "in total" in r.get_json()["error"]

    def test_item_type_count_is_capped(self, client, monkeypatch):
        monkeypatch.setattr(webapp, "MAX_ITEM_TYPES", 3)
        items = [{"id": str(i), "l": 1, "w": 1, "h": 1, "qty": 1} for i in range(4)]
        r = post(client, items)
        assert r.status_code == 400
        assert "Too many item types" in r.get_json()["error"]

    @pytest.mark.parametrize("bad", ["inf", "-inf", "nan"])
    def test_non_finite_dimensions_are_rejected(self, client, bad):
        """float('inf') is positive and would survive a naive > 0 check."""
        r = post(client, [{"id": "A", "l": bad, "w": 1, "h": 1, "qty": 1}])
        assert r.status_code == 400

    def test_absurd_dimensions_are_rejected(self, client):
        r = post(client, [{"id": "A", "l": 1, "w": 1, "h": 1, "qty": 1}],
                 box={"l": 1e9, "w": 1e9, "h": 1e9})
        assert r.status_code == 400

    def test_a_normal_problem_still_packs(self, client):
        r = post(client, [{"id": "A", "l": 6, "w": 5, "h": 4, "qty": 2}],
                 box={"l": 8, "w": 8, "h": 6})
        assert r.status_code == 200
        body = r.get_json()
        assert body["ok"] is True
        assert body["per_type"][0]["packed"] == 2
        assert body["search"]["truncated"] is False


class TestRateLimiting:
    def test_burst_is_allowed_then_throttled(self, client, monkeypatch):
        monkeypatch.setattr(webapp, "_limiter", webapp._TokenBucket(3, 60))
        body = [{"id": "A", "l": 1, "w": 1, "h": 1, "qty": 1}]
        assert [post(client, body).status_code for _ in range(3)] == [200, 200, 200]

        blocked = post(client, body)
        assert blocked.status_code == 429
        assert int(blocked.headers["Retry-After"]) >= 1
        assert blocked.get_json()["ok"] is False

    def test_tokens_refill(self):
        bucket = webapp._TokenBucket(1, 6000)      # 100/second
        assert bucket.check("ip") is None
        assert bucket.check("ip") is not None      # spent
        time.sleep(0.05)
        assert bucket.check("ip") is None          # refilled

    def test_clients_are_tracked_separately(self):
        bucket = webapp._TokenBucket(1, 1)
        assert bucket.check("a") is None
        assert bucket.check("b") is None           # b unaffected by a
        assert bucket.check("a") is not None

    def test_a_flood_of_new_clients_cannot_grow_the_table(self):
        """Tracking is itself a resource — one-shot keys must not exhaust it."""
        bucket = webapp._TokenBucket(1, 6000, max_tracked=100)
        for i in range(500):
            bucket.check(f"ip-{i}")
        assert len(bucket._buckets) <= 100

    def test_eviction_keeps_throttled_clients(self):
        """Being forgotten must not be a way to earn a fresh allowance."""
        bucket = webapp._TokenBucket(2, 1, max_tracked=50)
        bucket.check("heavy"); bucket.check("heavy")     # spends its burst
        assert bucket.check("heavy") is not None
        for i in range(200):                             # flood with new keys
            bucket.check(f"ip-{i}")
        assert bucket.check("heavy") is not None, "throttled client was forgotten"


class TestSearchBudget:
    HARD = [                                   # more than the box can hold
        {"id": "A", "l": 7, "w": 6, "h": 5, "qty": 60},
        {"id": "B", "l": 9, "w": 4, "h": 3, "qty": 60},
    ]

    def test_budget_bounds_a_hard_request(self, client, monkeypatch):
        monkeypatch.setattr(webapp, "PACK_TIME_BUDGET", 0.25)
        started = time.monotonic()
        r = post(client, self.HARD, box={"l": 20, "w": 20, "h": 20})
        elapsed = time.monotonic() - started

        assert r.status_code == 200
        body = r.get_json()
        assert body["ok"] is True
        assert body["search"]["truncated"] is True
        assert body["placements"], "a truncated search still returns a packing"
        assert elapsed < 5, f"budgeted search took {elapsed:.1f}s"

    def test_engine_returns_a_result_even_with_no_budget_left(self):
        """The first plan always runs, so there is always something to return."""
        items = [Item(id="A", dimensions=(7, 6, 5), quantity=60)]
        result = PackingEngine(Box((20, 20, 20)), items, time_budget=0.0).pack_all_items()
        assert sum(result.packed.values()) > 0
        assert result.search_truncated is True

    def test_unbudgeted_search_is_unchanged(self):
        items = [Item(id="A", dimensions=(6, 5, 4), quantity=2)]
        result = PackingEngine(Box((8, 8, 6)), items).pack_all_items()
        assert result.packed["A"] == 2
        assert result.search_truncated is False
