"""Minimal compatibility package for SPIKES' Python reference MNA boundary.

This standalone project intentionally does not import SPIKE PCB, field, project,
or desktop services.  The namespace is retained temporarily so released SPIKES
contracts do not change module identity during extraction.
"""

__version__ = "spikes-standalone-compat-1"

__all__: list[str] = []
