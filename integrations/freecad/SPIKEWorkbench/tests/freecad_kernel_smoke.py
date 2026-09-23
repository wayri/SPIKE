"""Run the SPIKE exchange path inside the real FreeCAD Python kernel."""

from __future__ import annotations

import sys
from pathlib import Path


WORKBENCH_ROOT = Path(__file__).resolve().parents[1]
if str(WORKBENCH_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKBENCH_ROOT))

import FreeCAD as App

from spike_freecad.contracts import load_geometry_exchange, validate_mechanical_exchange
from spike_freecad.freecad_geometry import (
    build_mechanical_exchange,
    exportable_objects,
    import_geometry_exchange,
)


def main() -> int:
    source = WORKBENCH_ROOT / "examples" / "example-geometry-exchange.json"
    payload = load_geometry_exchange(source)
    document = App.newDocument("SPIKEKernelSmoke")
    try:
        imported = import_geometry_exchange(document, payload, str(source))
        document.recompute()
        if len(imported) != len(payload["objects"]):
            raise RuntimeError("FreeCAD did not import every exchange object")
        for obj in imported:
            if obj.Shape.isNull() or float(obj.Shape.Volume) <= 0.0:
                raise RuntimeError(f"FreeCAD produced an invalid solid for {obj.Name}")

        exportable = exportable_objects(document, [])
        mechanical = build_mechanical_exchange(document, exportable)
        validate_mechanical_exchange(mechanical)
        if len(mechanical["objects"]) != 2:
            raise RuntimeError("Expected component-envelope and keepout exports")

        version = ".".join(str(value) for value in App.Version()[:3])
        total_volume = sum(float(obj.Shape.Volume) for obj in imported)
        print(
            "SPIKE FreeCAD kernel smoke passed: "
            f"FreeCAD {version}, {len(imported)} solids, "
            f"{len(mechanical['objects'])} mechanical exports, "
            f"{total_volume:.3f} mm^3 total volume"
        )
        return 0
    finally:
        App.closeDocument(document.Name)


if __name__ == "__main__":
    raise SystemExit(main())
