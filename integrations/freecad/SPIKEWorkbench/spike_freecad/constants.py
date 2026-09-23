"""Constants shared by the SPIKE FreeCAD workbench."""

import os


WORKBENCH_VERSION = "0.2.0"
GEOMETRY_CONTRACT = "spike/ecad-mcad-geometry/v1"
MECHANICAL_CONTRACT = "spike/ecad-mcad-mechanical/v1"
SCHEMA_VERSION = 1
SUPPORTED_UNITS = "mm"

OBJECT_ROLES = (
    "board",
    "copper",
    "component_envelope",
    "keepout",
    "mounting_hole",
    "mechanical",
    "air_volume",
    "reference",
)
EXPORT_ROLES = ("component_envelope", "keepout")

MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_DOCUMENT_NODES = 250_000
MAX_NESTING_DEPTH = 32
MAX_OBJECTS = 10_000
MAX_POLYGON_POINTS = 100_000
MAX_METADATA_ENTRIES = 64
MAX_STRING_LENGTH = 4096
MAX_ABS_COORDINATE_MM = 1_000_000.0
MAX_DIMENSION_MM = 1_000_000.0

PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON_ROOT = os.path.join(PACKAGE_ROOT, "Resources", "icons")

ROLE_COLORS = {
    "board": (0.18, 0.45, 0.29),
    "copper": (0.82, 0.48, 0.12),
    "component_envelope": (0.38, 0.67, 0.88),
    "keepout": (0.90, 0.25, 0.22),
    "mounting_hole": (0.55, 0.58, 0.62),
    "mechanical": (0.67, 0.70, 0.74),
    "air_volume": (0.35, 0.78, 0.90),
    "reference": (0.72, 0.72, 0.72),
}
