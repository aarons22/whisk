"""
Main entry point for the whisk module when run with `python -m whisk`
"""

from .cli import main

if __name__ == "__main__":
    exit(main())