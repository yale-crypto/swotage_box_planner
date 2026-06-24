"""
binpack — 3-D bin packing of multiple item types via maximal free-space partitioning.

Public API:

    from binpack import Box, Item, PackingEngine, print_report

    box = Box((30, 20, 10))
    items = [Item("A", (14, 25, 1), 12), Item("B", (5, 10, 2), 20)]
    result = PackingEngine(box, items).pack_all_items()
    print_report(result)
"""

from .geometry import BoxRegion
from .models import Box, Dimensions, Item, Placement, Position, Result
from .engine import PackingEngine
from .report import build_report, print_report
from .inputs import read_box, read_items, read_problem

__all__ = [
    "BoxRegion",
    "Box",
    "Item",
    "Placement",
    "Result",
    "Dimensions",
    "Position",
    "PackingEngine",
    "build_report",
    "print_report",
    "read_box",
    "read_items",
    "read_problem",
]
