"""
Optional matplotlib 3-D visualisation of a packing :class:`Result`.

Two clearly separated colour schemes so items and voids never blur together:

  • Box      — dashed blue wireframe outline.
  • Items    — SOLID, opaque cuboids; a distinct warm colour per item *type*.
  • Free     — TRANSLUCENT cuboids; a distinct cool colour per free region,
               with dashed coloured edges. Low alpha means items stay visible
               through them.

A legend maps every colour to its item type (with packed/requested counts) and
flags the free-space regions. matplotlib is imported lazily so the rest of the
package works without it.
"""

from __future__ import annotations

from .geometry import BoxRegion, fmt_triple
from .models import Result

# Warm, saturated — for placed items (one per item type).
ITEM_PALETTE = [
    "#e53935", "#fb8c00", "#fdd835", "#43a047", "#1e88e5",
    "#8e24aa", "#00897b", "#6d4c41", "#c0ca33", "#d81b60",
]
# Cool, light — for free-space regions (one per region).
FREE_PALETTE = [
    "#26c6da", "#9ccc65", "#7e57c2", "#42a5f5", "#ec407a",
    "#ffa726", "#66bb6a", "#5c6bc0", "#26a69a", "#ab47bc",
]


def _cuboid_faces(r: BoxRegion) -> list[list[tuple[float, float, float]]]:
    """The 6 quad faces of a region, as lists of 4 vertices."""
    x0, y0, z0 = r.x, r.y, r.z
    x1, y1, z1 = r.max_corner
    return [
        [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)],  # bottom
        [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)],  # top
        [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)],  # front
        [(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)],  # back
        [(x0, y0, z0), (x0, y1, z0), (x0, y1, z1), (x0, y0, z1)],  # left
        [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)],  # right
    ]


def _edges(r: BoxRegion) -> list[list[tuple[float, float, float]]]:
    """The 12 edges of a region (for a clean wireframe)."""
    return [face + [face[0]] for face in _cuboid_faces(r)]


def visualize(
    result: Result,
    *,
    draw_limit: int = 600,
    show_free: bool = True,
    free_limit: int = 40,
) -> None:
    """Open an interactive 3-D figure. Raises ImportError if matplotlib is absent."""
    try:
        import matplotlib.pyplot as plt
        from matplotlib.patches import Patch
        from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 — registers 3d projection
        from mpl_toolkits.mplot3d.art3d import Line3DCollection, Poly3DCollection
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "matplotlib is required for visualisation. Install with: pip install matplotlib"
        ) from exc

    box = result.box
    bl, bw, bh = box.dimensions

    fig = plt.figure(figsize=(11, 8))
    ax = fig.add_subplot(111, projection="3d")

    # One stable warm colour per item type.
    item_colour = {
        item_id: ITEM_PALETTE[i % len(ITEM_PALETTE)]
        for i, item_id in enumerate(result.requested)
    }

    # ── Box outline ─────────────────────────────────────────────────────────────
    ax.add_collection3d(
        Line3DCollection(
            _edges(BoxRegion(0, 0, 0, bl, bw, bh)),
            colors="#2840b0", linewidths=1.6, linestyles="--",
        )
    )

    # ── Placed items (solid, opaque, coloured by type) ──────────────────────────
    drawn = 0
    for p in result.placements:
        if drawn >= draw_limit:
            break
        ax.add_collection3d(
            Poly3DCollection(
                _cuboid_faces(p.as_region()),
                facecolors=item_colour.get(p.item_id, ITEM_PALETTE[0]),
                edgecolors="#111111", linewidths=0.4, alpha=1.0,
            )
        )
        drawn += 1

    # ── Free-space regions (translucent, each its own colour) ───────────────────
    free_drawn = 0
    if show_free:
        for i, r in enumerate(result.free_spaces):
            if free_drawn >= free_limit:
                break
            colour = FREE_PALETTE[i % len(FREE_PALETTE)]
            ax.add_collection3d(
                Poly3DCollection(
                    _cuboid_faces(r),
                    facecolors=colour, edgecolors=colour,
                    linewidths=1.0, linestyles=":", alpha=0.13,
                )
            )
            free_drawn += 1

    # ── Axes / proportions ──────────────────────────────────────────────────────
    ax.set_xlim(0, bl)
    ax.set_ylim(0, bw)
    ax.set_zlim(0, bh)
    try:
        ax.set_box_aspect((bl, bw, bh))  # true proportions (matplotlib >= 3.3)
    except Exception:  # pragma: no cover
        pass
    ax.set_xlabel("Length (x)")
    ax.set_ylabel("Width (y)")
    ax.set_zlabel("Height (z)")

    # ── Legend ──────────────────────────────────────────────────────────────────
    handles = [
        Patch(
            facecolor=item_colour[item_id], edgecolor="#111111",
            label=(
                f"Item {item_id}  {fmt_triple(result.sizes[item_id])}  "
                f"({result.packed[item_id]}/{result.requested[item_id]})"
            ),
        )
        for item_id in result.requested
    ]
    if show_free and result.free_spaces:
        shown = min(free_drawn, len(result.free_spaces))
        handles.append(
            Patch(
                facecolor=FREE_PALETTE[0], edgecolor=FREE_PALETTE[0], alpha=0.35,
                label=f"Free space ({shown} void{'s' if shown != 1 else ''}, translucent)",
            )
        )
    ax.legend(handles=handles, loc="upper left", fontsize=8, framealpha=0.9)

    note = "" if drawn >= len(result.placements) else f"  (showing {drawn} items)"
    ax.set_title(
        f"Box {fmt_triple(box.dimensions)}  ·  "
        f"{len(result.placements)} items packed  ·  "
        f"{result.utilization:.1f}% utilisation{note}",
        pad=14,
    )
    plt.tight_layout()
    plt.show()
