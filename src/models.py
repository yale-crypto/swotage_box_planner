"""
Core data models for the box packing calculator.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from itertools import permutations
from typing import NamedTuple


class Dims(NamedTuple):
    """An immutable (length, width, height) triple."""
    l: float
    w: float
    h: float

    def volume(self) -> float:
        return self.l * self.w * self.h

    def __str__(self) -> str:
        return f"{self.l} × {self.w} × {self.h}"


@dataclass(frozen=True)
class Box:
    dims: Dims

    @classmethod
    def from_values(cls, l: float, w: float, h: float) -> "Box":
        if any(v <= 0 for v in (l, w, h)):
            raise ValueError("Box dimensions must be positive.")
        return cls(Dims(l, w, h))

    @property
    def volume(self) -> float:
        return self.dims.volume()


@dataclass(frozen=True)
class Item:
    dims: Dims

    @classmethod
    def from_values(cls, l: float, w: float, h: float) -> "Item":
        if any(v <= 0 for v in (l, w, h)):
            raise ValueError("Item dimensions must be positive.")
        return cls(Dims(l, w, h))

    @property
    def volume(self) -> float:
        return self.dims.volume()

    def orientations(self) -> list[Dims]:
        """Return all unique axis-aligned orientations of the item."""
        seen: set[Dims] = set()
        unique: list[Dims] = []
        for perm in permutations((self.dims.l, self.dims.w, self.dims.h)):
            d = Dims(*perm)
            if d not in seen:
                seen.add(d)
                unique.append(d)
        return unique


@dataclass
class OrientationResult:
    """Packing outcome for a single item orientation."""
    orientation: Dims
    count_per_axis: tuple[int, int, int]   # (along L, along W, along H)
    total_count: int
    remaining_dims: Dims                    # leftover space after packing
    guillotine_bonus: int = 0              # extra items found by guillotine recursion

    @property
    def label(self) -> str:
        return str(self.orientation)


@dataclass
class PackingResult:
    """Full result returned by PackingCalculator."""
    box: Box
    item: Item
    best: OrientationResult
    all_orientations: list[OrientationResult]

    # Volume stats
    @property
    def used_volume(self) -> float:
        return self.item.volume * self.best.total_count

    @property
    def remaining_volume(self) -> float:
        return self.box.volume - self.used_volume

    @property
    def utilization_pct(self) -> float:
        return (self.used_volume / self.box.volume) * 100 if self.box.volume else 0.0

    # Gap analysis: could more items fit if geometry allowed?
    @property
    def theoretical_max(self) -> int:
        """Floor of box_volume / item_volume — pure volume upper bound."""
        if self.item.volume == 0:
            return 0
        return int(self.box.volume // self.item.volume)

    @property
    def geometry_gap(self) -> int:
        """Items that volume allows but geometry prevents."""
        return max(0, self.theoretical_max - self.best.total_count)
