"""PyInstaller entry point for the GUI.

Kept as a top-level script (not a package module) so PyInstaller has a plain
file to analyse; it imports the installed package and hands off to the GUI.
"""

from resolve_configurator.gui import main

if __name__ == "__main__":
    raise SystemExit(main())
