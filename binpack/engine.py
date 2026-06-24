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

import random
from dataclasses import dataclass

from .geometry import BoxRegion, fmt_triple, prune_regions
from .models import Box, Dimensions, Item, Placement, Result

# A score is compared lexicographically; smaller is better.
Score = tuple[float, float, float, float, float, float]


@dataclass
class _Attempt:
    """The outcome of one greedy pass over a particular unit ordering."""
    placed: int                      # how many units were placed
    used: float                      # total placed volume (tie-breaker)
    placements: list[Placement]
    packed: dict[str, int]
    free_spaces: list[BoxRegion]
    log: list[str]


class PackingEngine:
    def __init__(self, box: Box, items: list[Item]) -> None:
        self.box = box
        self.items = items

    # Multi-start search budget. A fixed seed keeps results reproducible.
    _MAX_RANDOM_STARTS: int = 400
    _RANDOM_SEED: int = 20240624

    # ── Public API ────────────────────────────────────────────────────────────
    def pack_all_items(self) -> Result:
        """
        Pack every requested unit and return the best :class:`Result` found.

        A single greedy pass is order-sensitive (largest-first can strand a
        small item in a thin leftover slab even when a valid full packing
        exists). So we run the greedy packer over several candidate orderings —
        a few deterministic ones plus seeded random restarts — and keep the
        arrangement that places the most units. The deterministic largest-first
        order is tried first, so the result is never worse than the old
        single-pass behaviour, and we stop early the moment every unit fits.
        """
        base: list[Item] = []
        for item in self.items:
            base.extend([item] * item.quantity)
        total = len(base)

        requested = {it.id: it.quantity for it in self.items}
        sizes: dict[str, Dimensions] = {it.id: it.dimensions for it in self.items}

        best: _Attempt | None = None
        for order in self._candidate_orders(base):
            attempt = self._pack_once(order)
            if best is None or (attempt.placed, attempt.used) > (best.placed, best.used):
                best = attempt
            if best.placed == total:
                break  # every unit placed — cannot do better

        assert best is not None  # _candidate_orders always yields ≥ 1 ordering
        self.box.free_spaces = best.free_spaces  # leave the winning partition
        return Result(
            box=self.box,
            placements=best.placements,
            requested=requested,
            packed=best.packed,
            sizes=sizes,
            free_spaces=best.free_spaces,
            log=best.log,
        )

    def _candidate_orders(self, base: list[Item]):
        """Yield unit orderings to try, cheapest/most-promising first (lazy)."""
        # Deterministic orders. Largest-volume-first is first → never worse than
        # the previous single-pass engine.
        yield sorted(base, key=lambda it: it.volume, reverse=True)
        yield sorted(base, key=lambda it: max(it.dimensions), reverse=True)
        yield sorted(base, key=lambda it: min(it.dimensions), reverse=True)
        yield sorted(base, key=lambda it: it.volume)            # smallest-first

        # Seeded random restarts, capped so runtime stays bounded on big inputs.
        total = max(1, len(base))
        n_random = min(self._MAX_RANDOM_STARTS, max(20, 6000 // total))
        rng = random.Random(self._RANDOM_SEED)
        for _ in range(n_random):
            shuffled = base[:]
            rng.shuffle(shuffled)
            yield shuffled

    def _pack_once(self, order: list[Item]) -> _Attempt:
        """Run one greedy pass over ``order`` on a fresh free-space partition."""
        l, w, h = self.box.dimensions
        self.box.free_spaces = [BoxRegion(0.0, 0.0, 0.0, l, w, h)]

        placements: list[Placement] = []
        packed = {it.id: 0 for it in self.items}
        log: list[str] = []
        used = 0.0

        for step, item in enumerate(order, start=1):
            placement = self.try_place_item(item)
            if placement is None:
                log.append(
                    f"[{step:>3}] SKIP  {item.id} {fmt_triple(item.dimensions)} "
                    f"— no free region can hold it (space fragmented)"
                )
                continue
            placements.append(placement)
            packed[item.id] += 1
            ol, ow, oh = placement.orientation
            used += ol * ow * oh
            self.update_free_spaces(placement.as_region())
            px, py, pz = placement.position
            log.append(
                f"[{step:>3}] PLACE {item.id} as {fmt_triple(placement.orientation)} "
                f"at ({px:g},{py:g},{pz:g})  ·  used region {placement.region_used}"
            )

        return _Attempt(
            placed=len(placements),
            used=used,
            placements=placements,
            packed=packed,
            free_spaces=list(self.box.free_spaces),
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
