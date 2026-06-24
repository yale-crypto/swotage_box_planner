"""
3D visualisation of packed items inside a box using matplotlib.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

import numpy as np

try:
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch
    from mpl_toolkits.mplot3d import Axes3D          # noqa: F401 – registers projection
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

if TYPE_CHECKING:
    from .models import PackingResult


def _cuboid_faces(
    ox: float, oy: float, oz: float,
    dx: float, dy: float, dz: float,
) -> list[list[list[float]]]:
    """Return the 6 faces of a cuboid as lists of 4 vertices each."""
    x0, x1 = ox, ox + dx
    y0, y1 = oy, oy + dy
    z0, z1 = oz, oz + dz
    return [
        [[x0,y0,z0],[x1,y0,z0],[x1,y1,z0],[x0,y1,z0]],  # bottom
        [[x0,y0,z1],[x1,y0,z1],[x1,y1,z1],[x0,y1,z1]],  # top
        [[x0,y0,z0],[x1,y0,z0],[x1,y0,z1],[x0,y0,z1]],  # front
        [[x0,y1,z0],[x1,y1,z0],[x1,y1,z1],[x0,y1,z1]],  # back
        [[x0,y0,z0],[x0,y1,z0],[x0,y1,z1],[x0,y0,z1]],  # left
        [[x1,y0,z0],[x1,y1,z0],[x1,y1,z1],[x1,y0,z1]],  # right
    ]


class Visualizer:
    """Renders a PackingResult as an interactive 3D matplotlib figure."""

    # Cap how many items we actually draw — beyond this the plot gets slow
    _DRAW_LIMIT = 200

    def __init__(self, result: "PackingResult") -> None:
        if not HAS_MPL:
            raise ImportError(
                "matplotlib is required for visualisation.\n"
                "Install it with:  pip install matplotlib"
            )
        self.result = result

    def show(self) -> None:
        fig = plt.figure(figsize=(10, 7))
        ax: Axes3D = fig.add_subplot(111, projection="3d")  # type: ignore[assignment]

        self._draw_box(ax)
        drawn = self._draw_items(ax)
        self._annotate(ax, drawn)

        ax.set_xlabel("Length")
        ax.set_ylabel("Width")
        ax.set_zlabel("Height")

        bx, bw, bh = self.result.box.dims
        ax.set_xlim(0, bx)
        ax.set_ylim(0, bw)
        ax.set_zlim(0, bh)

        plt.title(
            f"Box {self.result.box.dims}  ·  "
            f"Item {self.result.best.orientation}  ·  "
            f"{self.result.best.total_count} items  ·  "
            f"{self.result.utilization_pct:.1f}% utilisation",
            pad=14,
        )
        plt.tight_layout()
        plt.show()

    # ------------------------------------------------------------------
    # Private drawing helpers
    # ------------------------------------------------------------------

    def _draw_box(self, ax: "Axes3D") -> None:
        bx, bw, bh = self.result.box.dims
        faces = _cuboid_faces(0, 0, 0, bx, bw, bh)
        box_poly = Poly3DCollection(
            faces,
            alpha=0.04,
            facecolor="#88aaff",
            edgecolor="#3355cc",
            linewidths=1.5,
            linestyles="--",
        )
        ax.add_collection3d(box_poly)

    def _draw_items(self, ax: "Axes3D") -> int:
        il, iw, ih = self.result.best.orientation
        al, aw, ah = self.result.best.count_per_axis
        total = self.result.best.total_count

        # Colour palette — cycle through a few tones for depth perception
        colours = ["#ff7043", "#ffb74d", "#aed581", "#4dd0e1", "#ce93d8"]

        drawn = 0
        for li in range(al):
            for wi in range(aw):
                for hi in range(ah):
                    if drawn >= self._DRAW_LIMIT:
                        break
                    ox, oy, oz = li * il, wi * iw, hi * ih
                    colour = colours[(li + wi + hi) % len(colours)]
                    faces = _cuboid_faces(ox, oy, oz, il, iw, ih)
                    poly = Poly3DCollection(
                        faces,
                        alpha=0.55,
                        facecolor=colour,
                        edgecolor="#333333",
                        linewidths=0.4,
                    )
                    ax.add_collection3d(poly)
                    drawn += 1

        return drawn

    def _annotate(self, ax: "Axes3D", drawn: int) -> None:
        total = self.result.best.total_count
        if drawn < total:
            ax.text2D(
                0.02, 0.97,
                f"Showing {drawn} of {total} items (draw limit)",
                transform=ax.transAxes,
                fontsize=8,
                color="#888888",
                va="top",
            )
