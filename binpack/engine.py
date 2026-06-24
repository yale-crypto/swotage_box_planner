"""
Packing engine — the algorithm layer.

Strategy: greedy placement over a list of *maximal free spaces*.

  1. Free space starts as one region: the whole box.
  2. Items are expanded into individual units and sorted largest-volume first.
  3. Each unit is placed by searching every (free region × orientation) pair and
     scoring each candidate (see ``_score``). The best candidate wins.
  4. When an item is placed, EVERY free region it overlaps is carved up via
     ``split_after_placement`` (up to 6 new regions each), then the list is
     pruned of regions contained in others.

This is genuine 3-D space partitioning: an item is rejected only when no empty
cuboid can physically hold it — never on a volume-only basis. That is what lets
the engine show *why* items fail (space fragmentation) and how a smaller item
type can slot into voids a larger type left behind.
"""

from __future__ import annotations

from .geometry import BoxRegion, fmt_triple, prune_regions
from .models import Box, Dimensions, Item, Placement, Result

# A score is compared lexicographically; smaller is better.
Score = tuple[float, float, float, float, float, float]


class PackingEngine:
    def __init__(self, box: Box, items: list[Item]) -> None:
        self.box = box
        self.items = items

    # ── Public API ────────────────────────────────────────────────────────────
    def pack_all_items(self) -> Result:
        """Pack every requested unit and return a full :class:`Result`."""
        units: list[Item] = []
        for item in self.items:
            units.extend([item] * item.quantity)
        # Largest items first. Stable sort keeps same-type units grouped.
        units.sort(key=lambda it: it.volume, reverse=True)

        placements: list[Placement] = []
        packed: dict[str, int] = {it.id: 0 for it in self.items}
        requested: dict[str, int] = {it.id: it.quantity for it in self.items}
        sizes: dict[str, Dimensions] = {it.id: it.dimensions for it in self.items}
        log: list[str] = []

        for step, item in enumerate(units, start=1):
            placement = self.try_place_item(item)
            if placement is None:
                log.append(
                    f"[{step:>3}] SKIP  {item.id} {fmt_triple(item.dimensions)} "
                    f"— no free region can hold it (space fragmented)"
                )
                continue

            placements.append(placement)
            packed[item.id] += 1
            self.update_free_spaces(placement.as_region())
            px, py, pz = placement.position
            log.append(
                f"[{step:>3}] PLACE {item.id} as {fmt_triple(placement.orientation)} "
                f"at ({px:g},{py:g},{pz:g})  ·  used region {placement.region_used}"
            )

        return Result(
            box=self.box,
            placements=placements,
            requested=requested,
            packed=packed,
            sizes=sizes,
            free_spaces=self.box.free_spaces,
            log=log,
        )

    def try_place_item(self, item: Item) -> Placement | None:
        """Find the best (region, orientation) for one unit; ``None`` if none fit."""
        best: tuple[BoxRegion, Dimensions] | None = None
        best_score: Score | None = None

        for region in self.box.free_spaces:
            for orientation in item.orientations():
                if not region.can_fit(orientation):
                    continue
                score = self._score(region, orientation)
                if best_score is None or score < best_score:
                    best_score = score
                    best = (region, orientation)

        if best is None:
            return None

        region, orientation = best
        return Placement(
            item_id=item.id,
            position=(region.x, region.y, region.z),
            orientation=orientation,
            region_used=region.short(),
        )

    def update_free_spaces(self, item_box: BoxRegion) -> None:
        """Carve the placed item out of every overlapping free region, then prune."""
        rebuilt: list[BoxRegion] = []
        for region in self.box.free_spaces:
            if region.intersects(item_box):
                rebuilt.extend(region.split_after_placement(item_box))
            else:
                rebuilt.append(region)
        self.box.free_spaces = prune_regions(rebuilt)

    # ── Heuristic ─────────────────────────────────────────────────────────────
    @staticmethod
    def _score(region: BoxRegion, orientation: Dimensions) -> Score:
        """
        Lower is better. Encodes "maximise immediate fit + future usable space":

          1-3. Deepest-Bottom-Left: prefer the corner with the smallest
               (z, y, x). Packing into a corner keeps the remaining space as one
               large contiguous block rather than scattering small voids.
            4. Best-fit: among equal corners, prefer the *smallest* maximal
               region that still works, so large regions stay intact for big
               items still to come.
          5-6. Orientation tie-break: lay the item as flat as possible (least
               height, then largest footprint).
        """
        l, w, h = orientation
        return (region.z, region.y, region.x, region.volume, h, -(l * w))
