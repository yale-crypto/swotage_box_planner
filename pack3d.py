"""
3-D bin packing demo / entry point.

Run:
    python pack3d.py            # enter your own box + items interactively
    python pack3d.py --demo     # use the built-in example instead of prompting
    python pack3d.py --viz      # also open the matplotlib 3-D view
                                # (flags combine, e.g. --demo --viz)

The packing logic lives in the `binpack` package; this file just gathers the
input, runs the engine, and prints the result.
"""

from __future__ import annotations

import sys

from binpack import Box, Item, PackingEngine, print_report
from binpack.geometry import fmt_num
from binpack.inputs import read_problem


def _demo() -> tuple[Box, list[Item]]:
    """The example from the spec."""
    box = Box((30, 20, 10))
    items = [
        Item(id="A", dimensions=(14, 25, 1), quantity=12),
        Item(id="B", dimensions=(5, 10, 2), quantity=20),
    ]
    return box, items


def main() -> None:
    args = sys.argv[1:]
    do_viz = "--viz" in args

    try:
        if "--demo" in args:
            box, items = _demo()
        else:
            box, items = read_problem()
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.")
        return
    except ValueError as exc:
        print(f"\nInvalid input: {exc}")
        return

    result = PackingEngine(box, items).pack_all_items()
    print_report(result)

    # Generic explanation of any shortfall — always geometry, never volume.
    unplaced = sum(result.leftover(i) for i in result.requested)
    if unplaced:
        print(
            f"\n{unplaced} item(s) could not be placed. They were rejected on "
            f"geometry —\nno remaining empty cuboid could physically hold them — "
            f"not on volume\n(there are still {fmt_num(result.free_volume)} cubic "
            f"units free, just fragmented)."
        )

    if do_viz:
        try:
            from binpack.visualize import visualize

            visualize(result)
        except ImportError as exc:
            print(f"\nVisualisation unavailable: {exc}")


if __name__ == "__main__":
    main()
