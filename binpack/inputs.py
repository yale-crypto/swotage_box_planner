"""
Interactive console input for the box and the item types.

Prompt flow:

    Box dimensions (L W H):
    Number of item types (n):
    Item 1 dimensions (L W H):
    Item 1 quantity:
    ...
    Item n dimensions (L W H):
    Item n quantity:

Every prompt re-asks until it gets valid input, so a typo never crashes the run.
"""

from __future__ import annotations

from .models import Box, Dimensions, Item


def _read_floats3(prompt: str) -> Dimensions:
    """Read three positive numbers (space- or comma-separated)."""
    while True:
        raw = input(prompt).strip().replace(",", " ")
        parts = raw.split()
        if len(parts) == 3:
            try:
                vals = tuple(float(p) for p in parts)
            except ValueError:
                vals = None
            if vals is not None and all(v > 0 for v in vals):
                return vals  # type: ignore[return-value]
        print("  ⚠  enter three positive numbers, e.g.  30 20 10")


def _read_int(prompt: str, minimum: int = 1) -> int:
    """Read a whole number >= ``minimum``."""
    while True:
        raw = input(prompt).strip()
        try:
            value = int(raw)
        except ValueError:
            value = None
        if value is not None and value >= minimum:
            return value
        print(f"  ⚠  enter a whole number >= {minimum}")


def read_box() -> Box:
    return Box(_read_floats3("Box dimensions (L W H): "))


def read_items() -> list[Item]:
    n = _read_int("Number of item types (n): ", minimum=1)
    items: list[Item] = []
    for i in range(1, n + 1):
        print(f"\n-- Item {i} --")
        dims = _read_floats3(f"  Item {i} dimensions (L W H): ")
        qty = _read_int(f"  Item {i} quantity: ", minimum=1)
        items.append(Item(id=str(i), dimensions=dims, quantity=qty))
    return items


def read_problem() -> tuple[Box, list[Item]]:
    """Read a full problem (box + items) from the console."""
    box = read_box()
    print()
    items = read_items()
    return box, items
