"""Local corpus check: source import -> canonical save -> lossless Save As -> reopen.

Downloads are deliberately separate; this script never fetches or executes board
content. It writes only temporary packages, retaining input SHA-256 in stdout.
It does not qualify models, viewport pixels, mesh geometry, or solver physics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "python"))
from spike_core.service_project_handlers import handle_project_request
from spike_core import __version__


def check_board(path: Path) -> dict:
    data = path.read_bytes()
    snapshot = {
        "format": "spike-project-package/v2",
        "project": {"name": path.stem + ".spike"},
        "design": {"source_file": path.name, "source_board": data.decode("utf-8-sig"), "layers": [], "nets": []},
        "analysis": {"mode": "DC IR Drop", "pi_setup": {}},
    }
    started = time.perf_counter()

    def request(method, params):
        response = handle_project_request(method, params, request_id="corpus", application_version=__version__)
        if not response or not response.get("ok"):
            raise ValueError(json.dumps(response))
        return response["result"]

    with tempfile.TemporaryDirectory(prefix="spike-board-corpus-") as directory:
        original, duplicate = Path(directory) / "original.spike", Path(directory) / "save-as.spike"
        request("write_project_package", {"path": str(original), "snapshot": snapshot, "generate_geometry_tables": False})
        first = request("read_project_package", {"path": str(original)})
        request("write_project_package", {"path": str(duplicate), "base_package_path": str(original), "snapshot": snapshot, "generate_geometry_tables": False})
        second = request("read_project_package", {"path": str(duplicate)})
        assert first["canonical"]["design_ir"] == second["canonical"]["design_ir"], "DesignIR drift on Save As"
        assert second["project"]["design"]["source_board"] == snapshot["design"]["source_board"], "embedded source drift"
        design = second["canonical"]["design_ir"]
        return {"file": path.name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
                "status": "pass", "elapsed_s": round(time.perf_counter() - started, 3),
                "design_sections": sorted(design), "package_bytes": duplicate.stat().st_size}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("boards", type=Path, nargs="+")
    args = parser.parse_args()
    records = []
    for path in args.boards:
        try:
            records.append(check_board(path))
        except Exception as exc:
            records.append({"file": path.name, "status": "fail", "error": str(exc)})
    print(json.dumps({"scope": "import-save-saveas-reopen", "physics_qualified": False, "records": records}, indent=2))
    return int(any(record["status"] != "pass" for record in records))


if __name__ == "__main__":
    raise SystemExit(main())
