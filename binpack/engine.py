"""
Packing engine — the algorithm layer.

Strategy: greedy placement over a list of *maximal free spaces*.

  1. Free space starts as one region: the whole box.
  2. Items are expanded into individual units and sorted largest-volume first.
  3. Each unit is placed by searching every (free region × orientation) pair and
     scoring each candidate (see ``_STRATEGIES``). The best candidate wins.
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
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from itertools import cycle

from .geometry import BoxRegion, fmt_triple, prune_regions
from .models import Box, Dimensions, Item, Placement, Result

# A score is compared lexicographically; smaller is better.
Score = tuple[float, float, float, float, float, float]

# A placement heuristic: rank one (free region, orientation) candidate.
Strategy = Callable[["BoxRegion", "Dimensions"], Score]


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

        A single greedy pass is sensitive both to unit *order* (largest-first
        can strand a small item in a thin leftover slab) and to the *placement
        heuristic* — laying every item as flat as it will go wastes the box's
        height, and re-ordering identical units cannot undo that. So we run the
        greedy packer over several candidate plans: each unit ordering (a few
        deterministic ones plus seeded random restarts) paired with a placement
        strategy, keeping the arrangement that places the most units.

        Largest-first + the flat-lay strategy is tried first, so the result is
        never worse than the old single-pass behaviour, and we stop early the
        moment every unit fits.
        """
        base: list[Item] = []
        for item in self.items:
            base.extend([item] * item.quantity)
        total = len(base)

        requested = {it.id: it.quantity for it in self.items}
        sizes: dict[str, Dimensions] = {it.id: it.dimensions for it in self.items}

        best: _Attempt | None = None
        for order, strategy in self._candidate_plans(base):
            attempt = self._pack_once(order, strategy)
            if best is None or (attempt.placed, attempt.used) > (best.placed, best.used):
                best = attempt
            if best.placed == total:
                break  # every unit placed — cannot do better

        assert best is not None  # _candidate_plans always yields ≥ 1 plan
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

    def _candidate_plans(
        self, base: list[Item]
    ) -> Iterator[tuple[list[Item], Strategy]]:
        """
        Yield (ordering, strategy) plans to try, most-promising first (lazy).

        Plans are de-duplicated — one ordering under one strategy is a
        deterministic pass, so repeating it can only repeat its result. That
        matters most when the units are identical and every reshuffle collides.
        """
        default, *others = self._STRATEGIES
        seen: set[tuple] = set()

        def is_new(order: list[Item], strategy: Strategy) -> bool:
            key = (tuple((it.id, it.dimensions) for it in order), strategy)
            if key in seen:
                return False
            seen.add(key)
            return True

        def plan(order: list[Item], strategy: Strategy):
            return [(order, strategy)] if is_new(order, strategy) else []

        # 1. Deterministic orders, each under every strategy. Largest-volume
        #    first + flat-lay is first → never worse than a single old pass.
        deterministic = [
            sorted(base, key=lambda it: it.volume, reverse=True),
            sorted(base, key=lambda it: max(it.dimensions), reverse=True),
            sorted(base, key=lambda it: min(it.dimensions), reverse=True),
            sorted(base, key=lambda it: it.volume),              # smallest-first
        ]
        for order in deterministic:
            for strategy in self._STRATEGIES:
                yield from plan(order, strategy)

        # 2. Seeded random restarts under the default strategy — the previous
        #    engine's search, same seed and count, so we reproduce whatever it
        #    found and can only improve on it.
        total = max(1, len(base))
        n_random = min(self._MAX_RANDOM_STARTS, max(20, 6000 // total))
        rng = random.Random(self._RANDOM_SEED)
        shuffles: list[list[Item]] = []
        for _ in range(n_random):
            shuffled = base[:]
            rng.shuffle(shuffled)
            shuffles.append(shuffled)
            yield from plan(shuffled, default)

        # 3. Only if that still left units unplaced: revisit the first half of
        #    those restarts under the other strategies, one apiece, so the extra
        #    work is bounded well under a second full sweep.
        for strategy, shuffled in zip(cycle(others), shuffles[: n_random // 2]):
            yield from plan(shuffled, strategy)

    def _pack_once(self, order: list[Item], strategy: Strategy) -> _Attempt:
        """Run one greedy pass over ``order`` on a fresh free-space partition."""
        l, w, h = self.box.dimensions
        self.box.free_spaces = [BoxRegion(0.0, 0.0, 0.0, l, w, h)]

        placements: list[Placement] = []
        packed = {it.id: 0 for it in self.items}
        log: list[str] = []
        used = 0.0

        for step, item in enumerate(order, start=1):
            placement = self.try_place_item(item, strategy)
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

    def try_place_item(
        self, item: Item, strategy: Strategy | None = None
    ) -> Placement | None:
        """Find the best (region, orientation) for one unit; ``None`` if none fit."""
        score_fn = strategy or self._score_flat
        best: tuple[BoxRegion, Dimensions] | None = None
        best_score: Score | None = None

        for region in self.box.free_spaces:
            for orientation in item.orientations():
                if not region.can_fit(orientation):
                    continue
                score = score_fn(region, orientation)
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

    # ── Heuristics ────────────────────────────────────────────────────────────
    # Each strategy scores one (free region, orientation) candidate; lower wins.
    # Both share the same first four terms — Deepest-Bottom-Left plus best-fit —
    # and differ only in how they pose the item, because no single pose suits
    # every box: flat-lay fills wide shallow boxes, upright fills tall ones (two
    # 6×5×4 items fit an 8×8×6 box only standing on end).

    @staticmethod
    def _score_flat(region: BoxRegion, orientation: Dimensions) -> Score:
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

    @staticmethod
    def _score_upright(region: BoxRegion, orientation: Dimensions) -> Score:
        """
        As :meth:`_score_flat`, but stand the item up: greatest height, then
        smallest footprint. Trades floor area for headroom, which wins whenever
        two items can sit side by side only when both are on end.
        """
        l, w, h = orientation
        return (region.z, region.y, region.x, region.volume, -h, l * w)

    # Order matters: the first is tried first, so flat-lay stays the default.
    _STRATEGIES: tuple[Strategy, ...] = (_score_flat, _score_upright)
