# SPDX-License-Identifier: Apache-2.0
"""Exchange SPIKE's mesh with an external solver and import supplied samples.

This example demonstrates the protocol. It does not compute a voltage field.
Replace the sample input with the output of a solver using the supplied mesh or
solver_geometry, and retain the binding and provenance in the returned result.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))
from spike_extension_sdk import analysis_envelope, analysis_result, mesh_exchange, read_request, write_result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    request = read_request(args.request)
    if request.get("contribution_id") != "import-mesh-voltage-field":
        raise ValueError("Unsupported contribution")
    exchange = mesh_exchange(request)
    params = request["context"].get("parameters", {})
    samples = params.get("samples")
    if not isinstance(samples, list) or not samples:
        raise ValueError("Provide externally calculated samples in parameters.samples")
    mesh = exchange["mesh"]
    result = analysis_result(
        request,
        analysis_id=f"mesh-voltage-{request['request_id']}",
        mode="dc",
        model_status="unvalidated",
        solver=str(params.get("solver", "external-mesh-sample-import")),
        summary={"quantity": "voltage", "units": "V", "sample_count": len(samples),
                 "input_mesh_branches": mesh["branch_count"],
                 "mesh_preview_truncated": exchange["mesh_preview"]["truncated"]},
        visualization={"scalar_fields": {"voltage_v": samples},
                       "mesh": exchange["mesh_preview"]["cells"]},
        provenance={"visual_mesh_origin": "spike/mesh/v3-preview"},
        issues=[{"code": "EXTERNAL_FIELD_UNVALIDATED", "severity": "warning",
                 "message": "The supplied voltage samples have no independent physical validation."}],
    )
    write_result(args.result, analysis_envelope(result, title="External mesh voltage field"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
