"""
Engine-level tests for the `binpack` package.

(tests/test_packing.py covers the older single-type `src` calculator; this file
covers the multi-type space-partitioning engine.)

Run with:  pytest tests/ -v
"""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from binpack import Box, Item, PackingEngine
from binpack.geometry import BoxRegion


def pack(box_dims, specs):
    items = [Item(id=i, dimensions=d, quantity=q) for i, d, q in specs]
    return PackingEngine(Box(box_dims), items).pack_all_items()


class TestOrientationSearch:
    def test_upright_pose_is_found(self):
        """
        Two 6×5×4 items fit an 8×8×6 box only standing on end (two 5×4×6 poses
        side by side). Laying the first one flat — the default strategy — leaves
        no region big enough for the second, so the engine has to try the
        upright strategy as well.
        """
        result = pack((8, 8, 6), [("A", (6, 5, 4), 2)])
        assert result.packed["A"] == 2

    def test_placements_are_inside_the_box_and_disjoint(self):
        result = pack((8, 8, 6), [("A", (6, 5, 4), 2)])
        regions = [p.as_region() for p in result.placements]

        for r in regions:
            assert r.x >= 0 and r.y >= 0 and r.z >= 0
            assert (r.x + r.l, r.y + r.w, r.z + r.h) <= (8, 8, 6)

        for i, a in enumerate(regions):
            for b in regions[i + 1:]:
                assert not a.intersects(b)

    def test_impossible_item_is_still_rejected(self):
        """Diversity in the search must not let an oversized item through."""
        result = pack((8, 8, 6), [("A", (9, 9, 9), 1)])
        assert result.packed["A"] == 0
        assert result.placements == []


class TestNoRegression:
    def test_multi_type_demo_still_packs(self):
        result = pack((30, 20, 10), [("A", (14, 25, 1), 12), ("B", (5, 10, 2), 20)])
        assert result.packed["A"] == 10
        assert result.packed["B"] == 20

    def test_exact_fit_uses_the_whole_box(self):
        result = pack((4, 4, 4), [("A", (2, 2, 2), 8)])
        assert result.packed["A"] == 8
        assert result.free_volume == 0

    def test_results_are_deterministic(self):
        specs = [("A", (6, 5, 4), 2), ("B", (3, 3, 3), 5)]
        first = pack((10, 10, 8), specs)
        second = pack((10, 10, 8), specs)
        assert first.packed == second.packed
        assert [p.position for p in first.placements] == [
            p.position for p in second.placements
        ]
