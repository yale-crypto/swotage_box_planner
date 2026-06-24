"""
Unit tests for box_packer.

Run with:  pytest tests/ -v
"""

import sys, os, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.models import Box, Dims, Item, PackingResult
from src.calculator import PackingCalculator


# ─── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def ref_box():  return Box.from_values(30, 20, 10)
@pytest.fixture
def ref_item(): return Item.from_values(14, 25, 1)
@pytest.fixture
def ref_result(ref_box, ref_item):
    return PackingCalculator(ref_box, ref_item).calculate()


# ─── Dims ─────────────────────────────────────────────────────────────────────

class TestDims:
    def test_volume(self):        assert Dims(3, 4, 5).volume() == 60
    def test_str(self):           assert str(Dims(1, 2, 3)) == "1 × 2 × 3"
    def test_immutable(self):
        with pytest.raises(AttributeError):
            Dims(1, 2, 3).l = 9  # type: ignore


# ─── Box / Item construction ──────────────────────────────────────────────────

class TestConstruction:
    def test_valid_box(self):          assert Box.from_values(10, 20, 30).volume == 6000
    def test_zero_box_raises(self):
        with pytest.raises(ValueError): Box.from_values(0, 10, 10)
    def test_negative_box_raises(self):
        with pytest.raises(ValueError): Box.from_values(10, -5, 10)
    def test_valid_item(self):         assert Item.from_values(2, 3, 4).volume == 24
    def test_zero_item_raises(self):
        with pytest.raises(ValueError): Item.from_values(0, 1, 1)


# ─── Orientations ─────────────────────────────────────────────────────────────

class TestOrientations:
    def test_cube_has_one(self):
        assert len(Item.from_values(5, 5, 5).orientations()) == 1

    def test_square_base_has_three(self):
        assert len(Item.from_values(5, 5, 10).orientations()) == 3

    def test_all_different_has_six(self):
        assert len(Item.from_values(1, 2, 3).orientations()) == 6

    def test_orientations_preserve_volume(self):
        item = Item.from_values(2, 3, 7)
        vols = {o.volume() for o in item.orientations()}
        assert len(vols) == 1


# ─── Reference test case ──────────────────────────────────────────────────────

class TestReferenceCase:
    """Spec example: box 30×20×10, item 14×25×1 → 10 items."""

    def test_count(self, ref_result):        assert ref_result.best.total_count == 10
    def test_box_volume(self, ref_result):   assert ref_result.box.volume == 6000
    def test_item_volume(self, ref_result):  assert ref_result.item.volume == 350
    def test_used_volume(self, ref_result):  assert ref_result.used_volume == 3500
    def test_remaining(self, ref_result):    assert ref_result.remaining_volume == 2500
    def test_utilisation(self, ref_result):
        assert abs(ref_result.utilization_pct - 58.333) < 0.01
    def test_best_orientation_dims(self, ref_result):
        o = ref_result.best.orientation
        assert sorted([o.l, o.w, o.h]) == sorted([25, 14, 1])


# ─── Guillotine improves on simple grid ───────────────────────────────────────

class TestGuillotineImprovement:
    """Cases where guillotine beats a flat single-orientation grid."""

    def _simple_best(self, box, item):
        """Compute best simple-grid count (no guillotine) for comparison."""
        best = 0
        for o in item.orientations():
            c = (int(box.dims.l // o.l)
                 * int(box.dims.w // o.w)
                 * int(box.dims.h // o.h))
            best = max(best, c)
        return best

    def test_4x3x2_in_10x10x10(self):
        box, item = Box.from_values(10, 10, 10), Item.from_values(4, 3, 2)
        result = PackingCalculator(box, item).calculate()
        simple = self._simple_best(box, item)
        # Guillotine must find 36; simple finds 30
        assert result.best.total_count == 36
        assert result.best.total_count > simple

    def test_4x3x2_in_20x13x7(self):
        box, item = Box.from_values(20, 13, 7), Item.from_values(4, 3, 2)
        result = PackingCalculator(box, item).calculate()
        simple = self._simple_best(box, item)
        assert result.best.total_count == 70
        assert result.best.total_count > simple

    def test_4x3x2_in_15x10x6(self):
        box, item = Box.from_values(15, 10, 6), Item.from_values(4, 3, 2)
        result = PackingCalculator(box, item).calculate()
        simple = self._simple_best(box, item)
        assert result.best.total_count == 37
        assert result.best.total_count > simple

    def test_5x4x3_in_12x9x6(self):
        box, item = Box.from_values(12, 9, 6), Item.from_values(5, 4, 3)
        result = PackingCalculator(box, item).calculate()
        assert result.best.total_count == 10

    def test_guillotine_never_worse_than_simple(self):
        """Guillotine must always be >= simple grid for any input."""
        cases = [
            ((10, 10, 10), (3, 3, 3)),
            ((7, 7, 7), (3, 3, 3)),
            ((100, 80, 60), (7, 5, 3)),
            ((13, 11, 7), (4, 3, 2)),
            ((30, 20, 10), (14, 25, 1)),
        ]
        for (bl, bw, bh), (il, iw, ih) in cases:
            box  = Box.from_values(bl, bw, bh)
            item = Item.from_values(il, iw, ih)
            result = PackingCalculator(box, item).calculate()
            simple = self._simple_best(box, item)
            assert result.best.total_count >= simple, (
                f"Guillotine ({result.best.total_count}) < simple ({simple}) "
                f"for box {(bl,bw,bh)}, item {(il,iw,ih)}"
            )


# ─── Edge cases ───────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_exact_fit(self):
        result = PackingCalculator(
            Box.from_values(10, 10, 10), Item.from_values(10, 10, 10)
        ).calculate()
        assert result.best.total_count == 1
        assert result.utilization_pct == 100.0

    def test_item_too_large(self):
        result = PackingCalculator(
            Box.from_values(5, 5, 5), Item.from_values(6, 1, 1)
        ).calculate()
        assert result.best.total_count == 0

    def test_flat_items_in_flat_box(self):
        result = PackingCalculator(
            Box.from_values(100, 100, 1), Item.from_values(10, 10, 1)
        ).calculate()
        assert result.best.total_count == 100

    def test_geometry_gap_detected(self):
        # 3×3×3 box, item 2×2×2 → fits 1 by any single grid, volume allows 3
        result = PackingCalculator(
            Box.from_values(3, 3, 3), Item.from_values(2, 2, 2)
        ).calculate()
        assert result.geometry_gap > 0
        assert result.theoretical_max > result.best.total_count

    def test_all_orientation_results_returned(self):
        result = PackingCalculator(
            Box.from_values(10, 20, 30), Item.from_values(1, 2, 3)
        ).calculate()
        assert len(result.all_orientations) == 6


# ─── Volume invariants ────────────────────────────────────────────────────────

class TestVolumeInvariants:
    def test_utilisation_not_over_100(self):
        result = PackingCalculator(
            Box.from_values(10, 10, 10), Item.from_values(3, 3, 3)
        ).calculate()
        assert result.utilization_pct <= 100.0

    def test_remaining_non_negative(self):
        result = PackingCalculator(
            Box.from_values(7, 7, 7), Item.from_values(3, 3, 3)
        ).calculate()
        assert result.remaining_volume >= 0

    def test_used_plus_remaining_equals_box(self):
        result = PackingCalculator(
            Box.from_values(12, 8, 5), Item.from_values(3, 4, 2)
        ).calculate()
        assert abs(result.used_volume + result.remaining_volume - result.box.volume) < 1e-6
