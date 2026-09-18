from __future__ import annotations

import math
import os
import threading
import time
from typing import Any

from flask import Flask, jsonify, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix

from binpack import Box, Item, PackingEngine, build_report

# Stowage palette — first four match the design's item types A/B/C/D exactly
# (indigo / teal / orange / purple); the rest extend it so the first eight
# types stay clearly distinct from one another.
ITEM_PALETTE = [
    "#3360d8",  # blue
    "#11968c",  # teal
    "#d98a2b",  # orange
    "#7556c9",  # purple
    "#2f9e44",  # green
    "#e03131",  # red
    "#15aabf",  # cyan
    "#e64980",  # pink
    "#9c6644",  # brown
    "#f59f00",  # gold
]
FREE_COLOR = "#8c93a0"  # uniform slate for void regions (Stowage style)


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.environ.get(name, default)))
    except ValueError:
        return default


# ── Request limits ───────────────────────────────────────────────────────────
# Packing is CPU-bound and runs inside the request, so an unbounded request is
# an unbounded amount of work for the whole service. Two things bound it: these
# caps on problem size, and the search time budget below. Every value can be
# raised per-deployment through the environment.
MAX_ITEM_TYPES = _env_int("MAX_ITEM_TYPES", 40)
MAX_QTY_PER_TYPE = _env_int("MAX_QTY_PER_TYPE", 1000)
MAX_TOTAL_UNITS = _env_int("MAX_TOTAL_UNITS", 2000)
MAX_DIMENSION = _env_float("MAX_DIMENSION", 100_000.0)

# Seconds of *search* per request. The engine keeps the best arrangement it has
# found, so this trades a little packing quality for a bounded response time
# instead of failing. It is not a hard ceiling: the plan in flight finishes, so
# allow for one plan's overshoot when setting the gunicorn timeout above it.
PACK_TIME_BUDGET = _env_float("PACK_TIME_BUDGET_S", 5.0)

# ── Rate limiting ────────────────────────────────────────────────────────────
RATE_LIMIT_BURST = _env_int("RATE_LIMIT_BURST", 20)
RATE_LIMIT_PER_MINUTE = _env_int("RATE_LIMIT_PER_MINUTE", 60)
_RATE_LIMIT_MAX_TRACKED = 10_000


class _TokenBucket:
    """
    Per-client token bucket: ``burst`` requests at once, refilling at
    ``per_minute``.

    State lives in the worker process, so the effective limit is this times the
    worker count, and it resets when a worker recycles. That is the right shape
    for shedding a runaway client cheaply; a strict global limit would need
    shared storage (Redis) and a round trip on every request.
    """

    def __init__(self, burst: int, per_minute: int, max_tracked: int | None = None) -> None:
        self.burst = float(burst)
        self.rate = per_minute / 60.0        # tokens per second
        self.max_tracked = max_tracked or _RATE_LIMIT_MAX_TRACKED
        self._buckets: dict[str, tuple[float, float]] = {}   # key -> (tokens, at)
        self._lock = threading.Lock()

    def check(self, key: str) -> float | None:
        """``None`` if the request may proceed, else seconds until it may."""
        now = time.monotonic()
        with self._lock:
            tokens, seen = self._buckets.get(key, (self.burst, now))
            tokens = min(self.burst, tokens + (now - seen) * self.rate)
            if tokens < 1.0:
                self._buckets[key] = (tokens, now)
                return max(1.0, (1.0 - tokens) / self.rate) if self.rate else 60.0
            self._buckets[key] = (tokens - 1.0, now)
            if len(self._buckets) > self.max_tracked:
                self._evict(now)
            return None

    def _evict(self, now: float) -> None:
        """
        Make room by forgetting the *least throttled* clients first.

        A client whose bucket has refilled has spent nothing recently, so
        forgetting it costs nothing. A throttled client has to stay tracked:
        evicting it would hand it a fresh allowance, which is exactly what a
        flood of single-use keys would otherwise buy. Keeping a fixed fraction
        rather than only the refilled ones bounds the table against that flood.
        """
        level = lambda tokens, seen: min(self.burst, tokens + (now - seen) * self.rate)
        ranked = sorted(self._buckets.items(), key=lambda kv: level(*kv[1]))
        self._buckets = dict(ranked[: int(self.max_tracked * 0.8)])


_limiter = _TokenBucket(RATE_LIMIT_BURST, RATE_LIMIT_PER_MINUTE)

app = Flask(__name__)

# Behind a proxy (Render, any load balancer) the peer address is the proxy, so
# every client would share one rate-limit bucket. Trust X-Forwarded-For only
# when the deployment says how many hops to trust: a spoofable header must not
# be a way to get a fresh bucket per request.
_PROXY_HOPS = _env_int("TRUST_PROXY_HOPS", 0) if os.environ.get("TRUST_PROXY_HOPS") else 0
if _PROXY_HOPS:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=_PROXY_HOPS, x_proto=_PROXY_HOPS)


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.post("/api/pack")
def pack() -> Any:
    retry_after = _limiter.check(request.remote_addr or "unknown")
    if retry_after is not None:
        wait = int(math.ceil(retry_after))
        return (
            jsonify(ok=False, error=f"Too many packing requests — retry in {wait}s."),
            429,
            {"Retry-After": str(wait)},
        )

    payload = request.get_json(silent=True) or {}
    try:
        box, items = _parse_problem(payload)
    except (ValueError, TypeError, KeyError) as exc:
        return jsonify(ok=False, error=str(exc)), 400

    budget = PACK_TIME_BUDGET or None
    result = PackingEngine(box, items, time_budget=budget).pack_all_items()

    # Stable colour per item type (matches the matplotlib palette).
    colour = {
        item_id: ITEM_PALETTE[i % len(ITEM_PALETTE)]
        for i, item_id in enumerate(result.requested)
    }

    return jsonify(
        ok=True,
        summary={
            "box": list(box.dimensions),
            "box_volume": box.volume,
            "used_volume": result.used_volume,
            "free_volume": result.free_volume,
            "utilization": result.utilization,
            "placed_count": len(result.placements),
        },
        per_type=[
            {
                "id": item_id,
                "size": list(result.sizes[item_id]),
                "requested": result.requested[item_id],
                "packed": result.packed[item_id],
                "leftover": result.leftover(item_id),
                "color": colour[item_id],
            }
            for item_id in result.requested
        ],
        placements=[
            {
                "item_id": p.item_id,
                "position": list(p.position),
                "orientation": list(p.orientation),
                "color": colour.get(p.item_id, ITEM_PALETTE[0]),
            }
            for p in result.placements
        ],
        free_spaces=[
            {
                "origin": [r.x, r.y, r.z],
                "size": [r.l, r.w, r.h],
                "volume": r.volume,
                "color": FREE_COLOR,
            }
            for r in result.free_spaces
        ],
        log=result.log,
        report=build_report(result),
        search={"truncated": result.search_truncated, "budget_s": budget},
    )


def _parse_problem(payload: dict[str, Any]) -> tuple[Box, list[Item]]:
    """Validate the request body into a Box and a list of Items."""
    raw_box = payload.get("box") or {}
    box = Box(_dims(raw_box, "box"))

    raw_items = payload.get("items") or []
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("Add at least one item type.")
    if len(raw_items) > MAX_ITEM_TYPES:
        raise ValueError(
            f"Too many item types: {len(raw_items)} (limit {MAX_ITEM_TYPES})."
        )

    items: list[Item] = []
    seen: set[str] = set()
    total_units = 0
    for idx, raw in enumerate(raw_items, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"Item {idx}: malformed entry.")
        item_id = str(raw.get("id") or idx).strip() or str(idx)
        if item_id in seen:
            item_id = f"{item_id}#{idx}"
        seen.add(item_id)

        try:
            qty = int(raw.get("qty", 1))
        except (TypeError, ValueError):
            raise ValueError(f"Item {item_id}: quantity must be a whole number.")
        if qty < 1:
            raise ValueError(f"Item {item_id}: quantity must be at least 1.")
        if qty > MAX_QTY_PER_TYPE:
            raise ValueError(
                f"Item {item_id}: quantity {qty} exceeds the limit of {MAX_QTY_PER_TYPE}."
            )
        total_units += qty
        if total_units > MAX_TOTAL_UNITS:
            raise ValueError(
                f"Too many items in total: over {MAX_TOTAL_UNITS} units requested."
            )
        items.append(Item(id=item_id, dimensions=_dims(raw, f"item {item_id}"), quantity=qty))

    return box, items


def _dims(raw: dict[str, Any], what: str) -> tuple[float, float, float]:
    try:
        dims = (float(raw["l"]), float(raw["w"]), float(raw["h"]))
    except (KeyError, TypeError, ValueError):
        raise ValueError(f"{what}: needs numeric L, W and H.")
    if not all(math.isfinite(v) for v in dims):
        raise ValueError(f"{what}: dimensions must be real numbers.")
    if any(v <= 0 for v in dims):
        raise ValueError(f"{what}: dimensions must be positive.")
    if any(v > MAX_DIMENSION for v in dims):
        raise ValueError(f"{what}: dimensions must be {MAX_DIMENSION:g} or less.")
    return dims


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    debug = os.environ.get("DEBUG", "").lower() in {"1", "true", "yes"}
    print(f"\n  3-D Bin Packer running at  http://127.0.0.1:{port}\n  (Ctrl+C to stop)\n")
    app.run(host="127.0.0.1", port=port, debug=debug)


if __name__ == "__main__":
    main()
