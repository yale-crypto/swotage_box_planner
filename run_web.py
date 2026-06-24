"""
Launch the 3-D Bin Packer web UI.

    python run_web.py            # serve at http://127.0.0.1:8000
    PORT=5050 python run_web.py  # choose a port
    DEBUG=1 python run_web.py     # auto-reload while developing
"""

from webapp.app import main

if __name__ == "__main__":
    main()
