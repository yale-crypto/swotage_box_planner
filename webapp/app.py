"""
Flask backend for the 3-D bin packer web UI.

Routes
------
GET  /              → the single-page app
POST /api/pack      → run the packer on a JSON problem, return a JSON result
                      (summary, per-type table, placements + free voids for the
                      3-D scene, step log, and the full text report for export)

The heavy lifting stays in the `binpack` package; this module only adapts it to
HTTP and assigns stable colours (shared with the matplotlib view).
"""

from __future__ import annotations

import os
from typing import Any

from flask import Flask, jsonify, render_template, request

from binpack import Box, Item, PackingEngine, build_report

# Stowage palette — first four match the design's item types A/B/C/D exactly
# (indigo / teal / orange / purple); the rest extend it for additional types.
ITEM_PALETTE = [
    "#3360d8", "#11968c", "#d98a2b", "#7556c9", "#2f9e44",
    "#e8590c", "#c2255c", "#1098ad", "#5c7cfa", "#f08c00",
]
FREE_COLOR = "#8c93a0"  # uniform slate for void regions (Stowage style)

app = Flask(__name__)


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.post("/api/pack")
def pack() -> Any:
    payload = request.get_json(silent=True) or {}
    try:
        box, items = _parse_problem(payload)
    except (ValueError, TypeError, KeyError) as exc:
        return jsonify(ok=False, error=str(exc)), 400

    result = PackingEngine(box, items).pack_all_items()

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
    )


def _parse_problem(payload: dict[str, Any]) -> tuple[Box, list[Item]]:
    """Validate the request body into a Box and a list of Items."""
    raw_box = payload.get("box") or {}
    box = Box(_dims(raw_box, "box"))

    raw_items = payload.get("items") or []
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("Add at least one item type.")

    items: list[Item] = []
    seen: set[str] = set()
    for idx, raw in enumerate(raw_items, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"Item {idx}: malformed entry.")
        item_id = str(raw.get("id") or idx).strip() or str(idx)
        if item_id in seen:
            item_id = f"{item_id}#{idx}"
        seen.add(item_id)

        qty = int(raw.get("qty", 1))
        if qty < 1:
            raise ValueError(f"Item {item_id}: quantity must be at least 1.")
        items.append(Item(id=item_id, dimensions=_dims(raw, f"item {item_id}"), quantity=qty))

    return box, items


def _dims(raw: dict[str, Any], what: str) -> tuple[float, float, float]:
    try:
        dims = (float(raw["l"]), float(raw["w"]), float(raw["h"]))
    except (KeyError, TypeError, ValueError):
        raise ValueError(f"{what}: needs numeric L, W and H.")
    if any(v <= 0 for v in dims):
        raise ValueError(f"{what}: dimensions must be positive.")
    return dims


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    debug = os.environ.get("DEBUG", "").lower() in {"1", "true", "yes"}
    print(f"\n  3-D Bin Packer running at  http://127.0.0.1:{port}\n  (Ctrl+C to stop)\n")
    app.run(host="127.0.0.1", port=port, debug=debug)


if __name__ == "__main__":
    main()
