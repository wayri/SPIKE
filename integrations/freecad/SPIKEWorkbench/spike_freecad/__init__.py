"""SPIKE FreeCAD integration.

The contract parser is intentionally usable without FreeCAD so it can be
tested independently. FreeCAD and Part are imported only by GUI/geometry code.
"""

from .constants import WORKBENCH_VERSION

__all__ = ["WORKBENCH_VERSION"]

