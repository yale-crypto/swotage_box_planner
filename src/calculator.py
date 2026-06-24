"""
Packing calculator — guillotine-cut strategy.

Core idea
─────────
A single-orientation grid fill wastes the "leftover slabs" at the edges.
The guillotine algorithm fixes this:

  1. Fill the current region with the best-fitting orientation (primary grid).
  2. The primary grid leaves up to 3 rectangular slabs along the edges
     (one per axis).  These are *independent* sub-problems.
  3. Recurse into each sub-region and pack it the same way.
  4. Sum counts across all regions.

Compared to simple grid fill this always does at least as well and usually
better, because the edge slabs can accommodate a different orientation than
the primary region used.

Example: box 10×10×10, item 4×3×2
  Simple best:    2×3×5 = 30   (orientation 4×3×2)
  Guillotine:     30 + 6  = 36  (6 extra from 2×10×10 L-remainder)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from .models import Box, Dims, Item, OrientationResult, PackingResult


# ─── Guillotine sub-region ────────────────────────────────────────────────────

@dataclass
class Region:
    """A rectangular space to pack items into."""
    dims: Dims
    depth: int = 0          # recursion depth (for capping)
    count: int = 0          # items placed in this region
    orientation: Optional[Dims] = None
    children: list["Region"] = field(default_factory=list)


# ─── Calculator ───────────────────────────────────────────────────────────────

class PackingCalculator:
    """
    Calculates how many rectangular items fit inside a rectangular box.

    Algorithm: recursive guillotine cut with per-region orientation selection.
    """

    # Recursion cap — depth 6 always converges (verified empirically) and
    # keeps worst-case runtime under a millisecond for practical box sizes.
    _MAX_DEPTH: int = 6

    def __init__(self, box: Box, item: Item) -> None:
        self.box = box
        self.item = item

    # ── Public API ────────────────────────────────────────────────────────────

    def calculate(self) -> PackingResult:
        """
        Run the guillotine packer and return the full result.

        Also computes the simple-grid result for every orientation so the
        caller can display the orientation comparison table.
        """
        # Best guillotine count and the orientation that won the *root* region
        best_count, best_root_orientation, root_region = self._guillotine(
            self.box.dims, depth=0
        )

        # Build per-orientation results (simple grid, for the comparison table)
        orientation_results = [
            self._simple_grid(o) for o in self.item.orientations()
        ]

        # The "best orientation" shown to the user is the orientation that
        # produced the most items in the root region of the guillotine tree.
        best_simple = max(orientation_results, key=lambda r: r.total_count)

        # Use guillotine count if it exceeds the simple best
        if best_count > best_simple.total_count and best_root_orientation is not None:
            best_result = OrientationResult(
                orientation=best_root_orientation,
                count_per_axis=self._grid_counts(best_root_orientation, self.box.dims),
                total_count=best_count,
                remaining_dims=self._remaining(best_root_orientation, self.box.dims),
                guillotine_bonus=best_count - self._simple_count(best_root_orientation),
            )
        else:
            best_result = best_simple
            best_result.guillotine_bonus = 0

        return PackingResult(
            box=self.box,
            item=self.item,
            best=best_result,
            all_orientations=orientation_results,
        )

    # ── Guillotine recursion ──────────────────────────────────────────────────

    def _guillotine(
        self,
        region: Dims,
        depth: int,
    ) -> tuple[int, Optional[Dims], Optional[Region]]:
        """
        Pack `region` recursively.

        Returns (total_count, root_orientation, Region tree).
        """
        if depth > self._MAX_DEPTH:
            return 0, None, None

        rl, rw, rh = region
        if rl <= 0 or rw <= 0 or rh <= 0:
            return 0, None, None

        best_total = 0
        best_root_orient: Optional[Dims] = None
        best_node: Optional[Region] = None

        for o in self.item.orientations():
            nl, nw, nh = self._grid_counts(o, region)
            primary = nl * nw * nh
            if primary == 0:
                continue

            # Three non-overlapping slabs that cover leftover space.
            # ┌──────────────┬────────────┐
            # │   primary    │   slab_L   │  ← slab along L-remainder
            # ├──────┬───────┴────────────┤
            # │ sl_W │       sl_H         │  ← slabs along W and H remainders
            # └──────┴────────────────────┘
            slab_l = Dims(rl - nl * o.l, rw,       rh)
            slab_w = Dims(nl * o.l,      rw - nw * o.w, rh)
            slab_h = Dims(nl * o.l,      nw * o.w,      rh - nh * o.h)

            total = primary
            children: list[Region] = []

            for slab in (slab_l, slab_w, slab_h):
                if min(slab) > 0:
                    sub_count, _, sub_node = self._guillotine(slab, depth + 1)
                    total += sub_count
                    if sub_node is not None:
                        children.append(sub_node)

            if total > best_total:
                best_total = total
                best_root_orient = o
                best_node = Region(
                    dims=region,
                    depth=depth,
                    count=primary,
                    orientation=o,
                    children=children,
                )

        return best_total, best_root_orient, best_node

    # ── Simple grid (single orientation, no recursion) ────────────────────────

    def _simple_grid(self, orientation: Dims) -> OrientationResult:
        """Axis-aligned grid fill for one orientation — no guillotine."""
        counts = self._grid_counts(orientation, self.box.dims)
        total = counts[0] * counts[1] * counts[2]
        return OrientationResult(
            orientation=orientation,
            count_per_axis=counts,
            total_count=total,
            remaining_dims=self._remaining(orientation, self.box.dims),
            guillotine_bonus=0,
        )

    # ── Geometry helpers ──────────────────────────────────────────────────────

    def _grid_counts(self, o: Dims, region: Dims) -> tuple[int, int, int]:
        """How many items of orientation o fit along each axis of region."""
        return (
            int(region.l // o.l) if o.l > 0 else 0,
            int(region.w // o.w) if o.w > 0 else 0,
            int(region.h // o.h) if o.h > 0 else 0,
        )

    def _remaining(self, o: Dims, region: Dims) -> Dims:
        """Leftover space in region after placing the primary grid."""
        nl, nw, nh = self._grid_counts(o, region)
        return Dims(
            round(region.l - nl * o.l, 9),
            round(region.w - nw * o.w, 9),
            round(region.h - nh * o.h, 9),
        )

    def _simple_count(self, o: Dims) -> int:
        nl, nw, nh = self._grid_counts(o, self.box.dims)
        return nl * nw * nh

    # ── Gap explanation ───────────────────────────────────────────────────────

    @staticmethod
    def explain_geometry_gap(result: PackingResult) -> str:
        """Explain in plain English why leftover volume goes unpacked."""
        if result.geometry_gap == 0:
            return "No geometry gap — packing is volume-optimal."

        rem = result.best.remaining_dims
        fits = any(
            rem.l >= o.l and rem.w >= o.w and rem.h >= o.h
            for o in result.item.orientations()
        )

        lines = [
            f"Volume budget allows ~{result.theoretical_max} items; "
            f"geometry fits {result.best.total_count} "
            f"({result.geometry_gap} item-volume(s) lost to edge fragments)."
        ]
        if not fits:
            lines.append(
                f"The largest leftover slab {rem} cannot fit the item "
                f"({result.item.dims}) in any axis-aligned orientation."
            )
        return " ".join(lines)
