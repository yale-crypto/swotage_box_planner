"""
Geometry layer — pure spatial primitives, no packing logic.

A ``BoxRegion`` is an axis-aligned cuboid given by its minimum corner
``(x, y, z)`` and its size ``(l, w, h)`` along the x/y/z axes.

The free space inside a box is tracked as a list of *maximal* free regions
(Empty Maximal Spaces). These regions are allowed to overlap — that is the
whole point: every largest-possible empty cuboid is represented, so any item
that physically fits will fit at the corner of at least one region.
"""

from __future__ import annotations

from dataclasses import dataclass

# Numerical tolerance for float comparisons (inputs are usually integers).
EPS: float = 1e-9

Triple = tuple[float, float, float]


# ── Formatting helpers (lowest layer → reused everywhere) ─────────────────────

def fmt_num(v: float) -> str:
    """Compact number formatting: 5.0 -> '5', 2.5 -> '2.5'."""
    return f"{v:g}"


def fmt_triple(t: Triple) -> str:
    return "×".join(fmt_num(v) for v in t)


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    """Length of the 1-D overlap between [a0,a1] and [b0,b1] (negative if none)."""
    return min(a1, b1) - max(a0, b0)


@dataclass(frozen=True, slots=True)
class BoxRegion:
    """An axis-aligned cuboid of empty space."""

    x: float
    y: float
    z: float
    l: float  # size along x
    w: float  # size along y
    h: float  # size along z

    # ── Derived geometry ──────────────────────────────────────────────────────
    @property
    def volume(self) -> float:
        return self.l * self.w * self.h

    @property
    def max_corner(self) -> Triple:
        return (self.x + self.l, self.y + self.w, self.z + self.h)

    # ── Queries ───────────────────────────────────────────────────────────────
    def can_fit(self, dims: Triple) -> bool:
        """Does an item of size ``dims`` fit when placed at this region's corner?"""
        dl, dw, dh = dims
        return dl <= self.l + EPS and dw <= self.w + EPS and dh <= self.h + EPS

    def intersects(self, other: "BoxRegion") -> bool:
        """True if ``self`` and ``other`` share a *positive-volume* overlap."""
        ax1, ay1, az1 = self.max_corner
        bx1, by1, bz1 = other.max_corner
        return (
            _overlap(self.x, ax1, other.x, bx1) > EPS
            and _overlap(self.y, ay1, other.y, by1) > EPS
            and _overlap(self.z, az1, other.z, bz1) > EPS
        )

    def contains(self, other: "BoxRegion") -> bool:
        """True if ``self`` fully encloses ``other`` (used to prune redundancy)."""
        ax1, ay1, az1 = self.max_corner
        bx1, by1, bz1 = other.max_corner
        return (
            self.x <= other.x + EPS
            and self.y <= other.y + EPS
            and self.z <= other.z + EPS
            and ax1 >= bx1 - EPS
            and ay1 >= by1 - EPS
            and az1 >= bz1 - EPS
        )

    # ── Space partitioning ────────────────────────────────────────────────────
    def split_after_placement(self, item: "BoxRegion") -> list["BoxRegion"]:
        """
        Carve ``item`` out of ``self`` and return the resulting free regions.

        Produces up to **6** maximal sub-regions — one on each side of the
        placed item (left/right along x, front/back along y, bottom/top along z),
        each spanning the full extent of ``self`` on the two axes it does not cut.
        Sides where the item is flush with ``self`` contribute nothing.

        If ``item`` does not actually intersect ``self``, ``self`` is returned
        unchanged.
        """
        if not self.intersects(item):
            return [self]

        ax1, ay1, az1 = self.max_corner
        ix1, iy1, iz1 = item.max_corner
        pieces: list[BoxRegion] = []

        # Left / right slabs (cut along x)
        if item.x - self.x > EPS:
            pieces.append(BoxRegion(self.x, self.y, self.z, item.x - self.x, self.w, self.h))
        if ax1 - ix1 > EPS:
            pieces.append(BoxRegion(ix1, self.y, self.z, ax1 - ix1, self.w, self.h))

        # Front / back slabs (cut along y)
        if item.y - self.y > EPS:
            pieces.append(BoxRegion(self.x, self.y, self.z, self.l, item.y - self.y, self.h))
        if ay1 - iy1 > EPS:
            pieces.append(BoxRegion(self.x, iy1, self.z, self.l, ay1 - iy1, self.h))

        # Bottom / top slabs (cut along z)
        if item.z - self.z > EPS:
            pieces.append(BoxRegion(self.x, self.y, self.z, self.l, self.w, item.z - self.z))
        if az1 - iz1 > EPS:
            pieces.append(BoxRegion(self.x, self.y, iz1, self.l, self.w, az1 - iz1))

        return pieces

    # ── Display ───────────────────────────────────────────────────────────────
    def short(self) -> str:
        return (
            f"{fmt_triple((self.l, self.w, self.h))}"
            f"@({fmt_num(self.x)},{fmt_num(self.y)},{fmt_num(self.z)})"
        )

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.short()


def prune_regions(regions: list[BoxRegion]) -> list[BoxRegion]:
    """
    Drop empty regions and any region fully contained in another.

    Containment ties (identical regions) are broken by list index so exactly one
    copy survives. This keeps the maximal-space list from growing without bound.
    """
    regs = [r for r in regions if r.volume > EPS]
    keep: list[BoxRegion] = []
    for i, r in enumerate(regs):
        redundant = False
        for j, other in enumerate(regs):
            if i == j:
                continue
            if other.contains(r):
                # `other` strictly bigger, or equal size but earlier in the list.
                if other.volume > r.volume + EPS or (
                    abs(other.volume - r.volume) <= EPS and j < i
                ):
                    redundant = True
                    break
        if not redundant:
            keep.append(r)
    return keep
