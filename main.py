"""SafeRoute Final Edition launcher.

The original Tkinter interface is retained as legacy_main.py. The default
application is now the hybrid desktop experience powered by pywebview + FastAPI.
"""
from hybrid_app import main

if __name__ == "__main__":
    main()
