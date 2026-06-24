"""Entry point.

  python main.py          # interactive command-line interface
  python main.py --gui    # simple graphical interface
"""

import sys
import os

# Allow running from the project root without installing
sys.path.insert(0, os.path.dirname(__file__))

if __name__ == "__main__":
    if "--gui" in sys.argv[1:]:
        from src.gui import run_gui
        run_gui()
    else:
        from src.cli import run_cli
        run_cli()
