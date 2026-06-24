"""
Command-line interface and results display for the box packer.
"""

from __future__ import annotations
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import PackingResult


# ── ANSI colour helpers ───────────────────────────────────────────────────────
def _bold(s: str) -> str:   return f"\033[1m{s}\033[0m"
def _green(s: str) -> str:  return f"\033[92m{s}\033[0m"
def _yellow(s: str) -> str: return f"\033[93m{s}\033[0m"
def _dim(s: str) -> str:    return f"\033[2m{s}\033[0m"
def _cyan(s: str) -> str:   return f"\033[96m{s}\033[0m"
def _hr(char: str = "─", width: int = 62) -> str: return char * width


# ── Orientation table ─────────────────────────────────────────────────────────

def print_orientation_table(result: "PackingResult") -> None:
    rows = result.all_orientations
    best_count = max(r.total_count for r in rows)  # simple-grid best

    header = (
        f"{'Orientation (L×W×H)':<22} "
        f"{'Along L':>7} {'Along W':>7} {'Along H':>7} "
        f"{'Grid':>6} {'+ Guillotine':>13}"
    )
    print()
    print(_bold("  All Orientations  (simple grid fill)"))
    print("  " + _hr())
    print("  " + _dim(header))
    print("  " + _hr())

    for r in sorted(rows, key=lambda x: -x.total_count):
        marker = " ✓" if r.total_count == best_count else "  "
        colour = _green if r.total_count == best_count else (lambda s: s)
        al, aw, ah = r.count_per_axis
        bonus_str = ""
        if hasattr(r, "guillotine_bonus") and r.guillotine_bonus > 0:
            bonus_str = _cyan(f"+{r.guillotine_bonus}")
        line = (
            f"{str(r.orientation):<22} "
            f"{al:>7} {aw:>7} {ah:>7} "
            f"{r.total_count:>6}  {bonus_str}"
        )
        print(colour(f"{marker} {line}"))

    print("  " + _hr())


# ── Summary block ─────────────────────────────────────────────────────────────

def print_summary(result: "PackingResult") -> None:
    b = result.best
    bonus = getattr(b, "guillotine_bonus", 0)

    print()
    print(_bold("  Packing Summary"))
    print("  " + _hr())

    def row(label: str, value: str) -> None:
        print(f"  {_dim(label + ':'):<32} {value}")

    row("Best orientation (L×W×H)", _green(_bold(str(b.orientation))))
    row("Items along L / W / H",    " × ".join(str(n) for n in b.count_per_axis))
    if bonus > 0:
        row("Grid fill",     str(b.total_count - bonus))
        row("Guillotine bonus",  _cyan(f"+{bonus} (from edge slabs)"))
    row("Maximum items that fit",   _bold(_green(str(b.total_count))))
    print("  " + _hr())
    row("Box volume",              f"{result.box.volume:,.2f}")
    row("Item volume",             f"{result.item.volume:,.2f}")
    row("Used volume",             f"{result.used_volume:,.2f}")
    row("Remaining volume",        f"{result.remaining_volume:,.2f}")
    row("Utilisation",             _yellow(f"{result.utilization_pct:.2f}%"))
    print("  " + _hr())
    row("Remaining space (L×W×H)", str(b.remaining_dims))

    if result.geometry_gap > 0:
        print()
        print(_bold("  ⚠  Geometry Gap"))
        print("  " + _hr())
        print(f"  Volume budget allows {result.theoretical_max} items,")
        print(f"  guillotine packs     {b.total_count}.")
        print(f"  Gap: {result.geometry_gap} item-volume(s) lost to unfillable edge fragments.")

    print("  " + _hr())


# ── Input prompts ─────────────────────────────────────────────────────────────

def prompt_dims(label: str) -> tuple[float, float, float]:
    while True:
        raw = input(f"  {label} (L W H, space-separated): ").strip()
        parts = raw.split()
        if len(parts) == 3:
            try:
                vals = tuple(float(p) for p in parts)
                if all(v > 0 for v in vals):
                    return vals  # type: ignore[return-value]
            except ValueError:
                pass
        print("  ⚠  Enter three positive numbers, e.g.:  30 20 10")


def prompt_yes_no(question: str, default: bool = True) -> bool:
    hint = "[Y/n]" if default else "[y/N]"
    raw = input(f"  {question} {hint}: ").strip().lower()
    if raw == "":
        return default
    return raw.startswith("y")


# ── Top-level runner ──────────────────────────────────────────────────────────

def run_cli() -> None:
    from .models import Box, Item
    from .calculator import PackingCalculator
    from .visualizer import Visualizer

    print()
    print(_bold("╔══════════════════════════════════════╗"))
    print(_bold("║      Box Packing Calculator          ║"))
    print(_bold("╚══════════════════════════════════════╝"))
    print()

    try:
        box_dims  = prompt_dims("Box  dimensions")
        item_dims = prompt_dims("Item dimensions")
    except (KeyboardInterrupt, EOFError):
        print("\n  Aborted.")
        sys.exit(0)

    try:
        box  = Box.from_values(*box_dims)
        item = Item.from_values(*item_dims)
    except ValueError as exc:
        print(f"\n  Error: {exc}")
        sys.exit(1)

    calc   = PackingCalculator(box, item)
    result = calc.calculate()

    print_orientation_table(result)
    print_summary(result)

    try:
        if prompt_yes_no("Show 3D visualisation?"):
            Visualizer(result).show()
    except ImportError as exc:
        print(f"\n  Visualisation unavailable: {exc}")
    except (KeyboardInterrupt, EOFError):
        pass
