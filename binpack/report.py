"""
Text reporting — turns a :class:`Result` into the four console sections the spec
asks for. ``build_report`` returns the text as a string (reused by the web app's
"Download report" export); ``print_report`` just prints it.
"""

from __future__ import annotations

from .geometry import fmt_num, fmt_triple
from .models import Result

_WIDTH = 64


def _rule(char: str = "─") -> str:
    return char * _WIDTH


def build_report(result: Result, *, max_log_lines: int | None = None) -> str:
    """Render the full report as a single string."""
    box = result.box
    out: list[str] = []

    out.append(_rule("═"))
    out.append(f" 3D BIN PACKING RESULT   box = {fmt_triple(box.dimensions)}")
    out.append(_rule("═"))

    # 1 ── Packing summary ──────────────────────────────────────────────────────
    out.append("")
    out.append("1. Packing summary")
    out.append(_rule())
    out.append(f"  Total box volume   : {fmt_num(box.volume)}")
    out.append(f"  Total used volume  : {fmt_num(result.used_volume)}")
    out.append(f"  Free volume        : {fmt_num(result.free_volume)}")
    out.append(f"  Utilisation        : {result.utilization:.2f}%")
    out.append(f"  Items placed       : {len(result.placements)}")

    # 2 ── Per item type ────────────────────────────────────────────────────────
    out.append("")
    out.append("2. Per item type")
    out.append(_rule())
    out.append(f"  {'ID':<6}{'Size (L×W×H)':<18}{'Requested':>10}{'Packed':>8}{'Leftover':>10}")
    for item_id in result.requested:
        req = result.requested[item_id]
        pk = result.packed[item_id]
        size = fmt_triple(result.sizes[item_id])
        out.append(f"  {item_id:<6}{size:<18}{req:>10}{pk:>8}{result.leftover(item_id):>10}")

    # 3 ── Free-space report ─────────────────────────────────────────────────────
    out.append("")
    out.append("3. Remaining free space (maximal voids)")
    out.append(_rule())
    if not result.free_spaces:
        out.append("  (none — box completely filled)")
    else:
        out.append("  Note: these are *maximal* empty cuboids and may overlap, so their")
        out.append("  volumes do not sum to the free volume above.")
        out.append("")
        out.append(f"  {'#':<4}{'origin (x,y,z)':<22}{'size (L×W×H)':<20}{'volume':>10}")
        for i, r in enumerate(result.free_spaces, start=1):
            origin = f"({fmt_num(r.x)},{fmt_num(r.y)},{fmt_num(r.z)})"
            size = fmt_triple((r.l, r.w, r.h))
            out.append(f"  {i:<4}{origin:<22}{size:<20}{fmt_num(r.volume):>10}")

    # 4 ── Step-by-step log ──────────────────────────────────────────────────────
    out.append("")
    out.append("4. Step-by-step placement log")
    out.append(_rule())
    lines = result.log
    shown = lines if max_log_lines is None else lines[:max_log_lines]
    for line in shown:
        out.append("  " + line)
    if max_log_lines is not None and len(lines) > max_log_lines:
        out.append(f"  … {len(lines) - max_log_lines} more step(s) omitted")

    out.append("")
    out.append(_rule("═"))
    return "\n".join(out)


def print_report(result: Result, *, max_log_lines: int | None = None) -> None:
    """Print the four required sections to stdout."""
    print(build_report(result, max_log_lines=max_log_lines))
