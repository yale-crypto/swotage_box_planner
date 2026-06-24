"""
Minimal Tkinter GUI for the box packing calculator.

Plain and functional: enter box + item dimensions, click Calculate,
read the result. No styling beyond Tk defaults.

Run with:  python main.py --gui
"""

from __future__ import annotations
import tkinter as tk
from tkinter import ttk

from .models import Box, Item
from .calculator import PackingCalculator


def _parse(entry_l: tk.Entry, entry_w: tk.Entry, entry_h: tk.Entry) -> tuple[float, float, float]:
    """Read three entry widgets as positive floats, or raise ValueError."""
    vals = tuple(float(e.get().strip()) for e in (entry_l, entry_w, entry_h))
    if any(v <= 0 for v in vals):
        raise ValueError("Dimensions must be positive numbers.")
    return vals  # type: ignore[return-value]


def run_gui() -> None:
    root = tk.Tk()
    root.title("Box Packing Calculator")

    main = ttk.Frame(root, padding=12)
    main.grid(row=0, column=0, sticky="nsew")
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)

    # ── Input rows ────────────────────────────────────────────────────────────
    def dim_row(parent: ttk.Frame, label: str, r: int) -> tuple[tk.Entry, tk.Entry, tk.Entry]:
        ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", pady=4)
        entries = []
        for c, name in enumerate(("L", "W", "H"), start=1):
            ttk.Label(parent, text=name).grid(row=r, column=c * 2 - 1, padx=(8, 2))
            e = ttk.Entry(parent, width=8)
            e.grid(row=r, column=c * 2, padx=(0, 4))
            entries.append(e)
        return tuple(entries)  # type: ignore[return-value]

    box_l, box_w, box_h = dim_row(main, "Box dimensions", 0)
    item_l, item_w, item_h = dim_row(main, "Item dimensions", 1)

    # ── Result display ────────────────────────────────────────────────────────
    result_box = tk.Text(main, width=52, height=16, wrap="word")
    result_box.grid(row=3, column=0, columnspan=7, pady=(10, 0), sticky="nsew")
    result_box.configure(state="disabled")
    main.rowconfigure(3, weight=1)
    main.columnconfigure(6, weight=1)

    def show(text: str) -> None:
        result_box.configure(state="normal")
        result_box.delete("1.0", "end")
        result_box.insert("1.0", text)
        result_box.configure(state="disabled")

    # ── Calculate action ──────────────────────────────────────────────────────
    def calculate() -> None:
        try:
            box = Box.from_values(*_parse(box_l, box_w, box_h))
            item = Item.from_values(*_parse(item_l, item_w, item_h))
        except ValueError:
            show("Error: enter three positive numbers for each of box and item.")
            return

        result = PackingCalculator(box, item).calculate()
        b = result.best
        bonus = getattr(b, "guillotine_bonus", 0)

        lines = [
            f"Maximum items that fit: {b.total_count}",
            "",
            f"Best orientation (L x W x H): {b.orientation}",
            f"Items along L / W / H: {' x '.join(str(n) for n in b.count_per_axis)}",
        ]
        if bonus > 0:
            lines.append(f"Grid fill: {b.total_count - bonus}  (+{bonus} from edge slabs)")
        lines += [
            "",
            f"Box volume:        {result.box.volume:,.2f}",
            f"Item volume:       {result.item.volume:,.2f}",
            f"Used volume:       {result.used_volume:,.2f}",
            f"Remaining volume:  {result.remaining_volume:,.2f}",
            f"Utilisation:       {result.utilization_pct:.2f}%",
            "",
            f"Remaining space (L x W x H): {b.remaining_dims}",
        ]
        if result.geometry_gap > 0:
            lines += [
                "",
                f"Geometry gap: volume allows {result.theoretical_max} items, "
                f"geometry fits {b.total_count} "
                f"({result.geometry_gap} lost to edge fragments).",
            ]

        show("\n".join(lines))

    btns = ttk.Frame(main)
    btns.grid(row=2, column=0, columnspan=7, pady=(10, 0), sticky="w")
    ttk.Button(btns, text="Calculate", command=calculate).grid(row=0, column=0)
    ttk.Button(btns, text="Quit", command=root.destroy).grid(row=0, column=1, padx=(8, 0))

    root.bind("<Return>", lambda _event: calculate())
    box_l.focus_set()
    root.mainloop()
