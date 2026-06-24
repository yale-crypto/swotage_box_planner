"""
Data models — the nouns of the system.

Kept deliberately free of algorithm logic; the engine (engine.py) drives these.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import permutations

from .geometry import BoxRegion, Triple, fmt_triple

Dimensions = Triple
Position = Triple


@dataclass(frozen=True, slots=True)
class Item:
    """A type of item to pack, with a requested quantity."""

    id: str
    dimensions: Dimensions
    quantity: int = 1

    def __post_init__(self) -> None:
        if any(v <= 0 for v in self.dimensions):
            raise ValueError(f"Item {self.id!r}: dimensions must be positive.")
        if self.quantity < 0:
            raise ValueError(f"Item {self.id!r}: quantity must be non-negative.")

    @property
    def volume(self) -> float:
        l, w, h = self.dimensions
        return l * w * h

    def orientations(self) -> list[Dimensions]:
        """
        All unique axis-aligned orientations (up to 6).

        Ordered to prefer a flat pose first (smallest height, then largest
        footprint), which gives the greedy engine a sensible default tie-break.
        """
        seen: set[Dimensions] = set()
        unique: list[Dimensions] = []
        for perm in permutations(self.dimensions):
            if perm not in seen:
                seen.add(perm)
                unique.append(perm)
        unique.sort(key=lambda d: (d[2], -(d[0] * d[1])))
        return unique


@dataclass
class Box:
    """The container. Holds its own list of free regions."""

    dimensions: Dimensions
    free_spaces: list[BoxRegion] = field(default_factory=list)

    def __post_init__(self) -> None:
        if any(v <= 0 for v in self.dimensions):
            raise ValueError("Box dimensions must be positive.")
        if not self.free_spaces:
            l, w, h = self.dimensions
            self.free_spaces = [BoxRegion(0.0, 0.0, 0.0, l, w, h)]

    @property
    def volume(self) -> float:
        l, w, h = self.dimensions
        return l * w * h


@dataclass(frozen=True, slots=True)
class Placement:
    """A single placed item: which type, where, in what orientation."""

    item_id: str
    position: Position
    orientation: Dimensions
    region_used: str  # human-readable label of the free region consumed

    @property
    def volume(self) -> float:
        l, w, h = self.orientation
        return l * w * h

    def as_region(self) -> BoxRegion:
        """The occupied space as a region (for collision / splitting)."""
        x, y, z = self.position
        l, w, h = self.orientation
        return BoxRegion(x, y, z, l, w, h)

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        x, y, z = self.position
        return f"{self.item_id} {fmt_triple(self.orientation)} @ ({x:g},{y:g},{z:g})"


@dataclass
class Result:
    """Everything the caller needs to inspect or render the outcome."""

    box: Box
    placements: list[Placement]
    requested: dict[str, int]
    packed: dict[str, int]
    sizes: dict[str, Dimensions]
    free_spaces: list[BoxRegion]
    log: list[str]

    @property
    def used_volume(self) -> float:
        return sum(p.volume for p in self.placements)

    @property
    def free_volume(self) -> float:
        """True remaining volume (box minus everything placed)."""
        return self.box.volume - self.used_volume

    @property
    def utilization(self) -> float:
        return 100.0 * self.used_volume / self.box.volume if self.box.volume else 0.0

    def leftover(self, item_id: str) -> int:
        return self.requested[item_id] - self.packed[item_id]
