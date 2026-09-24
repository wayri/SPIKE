"""Example adapter: exchange normalized board data and externally computed samples.

The caller must provide real samples in context.parameters.samples. This
adapter does not solve electrical physics or invent a field for the board.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))
from spike_extension_sdk import analysis_envelope, analysis_result, read_request, write_result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    request = read_request(args.request)
    if request.get("contribution_id") != "import-voltage-field":
        raise ValueError("Unsupported contribution")
    context = request["context"]
    design = context["design"]
    if design.get("contract") != "spike/v1" or design.get("units") != "mm":
        raise ValueError("A normalized millimetre DesignIR is required")
    parameters = context.get("parameters", {})
    samples = parameters.get("samples")
    if not isinstance(samples, list) or not samples:
        raise ValueError("Provide external voltage samples in parameters.samples")
    result = analysis_result(
        request,
        analysis_id=f"external-voltage-{request['request_id']}",
        mode="dc",
        model_status="unvalidated",
        solver=str(parameters.get("solver", "external-sample-import")),
        summary={"sample_count": len(samples), "quantity": "voltage", "units": "V"},
        visualization={"scalar_fields": {"voltage_v": samples}},
        issues=[{"code": "EXTERNAL_FIELD_UNVALIDATED", "severity": "warning",
                 "message": "Imported samples have not been independently checked against the board."}],
    )
    write_result(args.result, analysis_envelope(result, title="External voltage field"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
