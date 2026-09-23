"""Compatibility entry point for the versioned SPIKE command-line interface."""

from .spike_core.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
