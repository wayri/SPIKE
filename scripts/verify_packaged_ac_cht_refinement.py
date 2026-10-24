# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
"""Replay all six gated AC/CHT refinement inputs through an actual frozen worker.

This is transport/field equivalence to retained analytical qualification, not
another independent physical reference or production qualification.
"""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.build_packaged_worker import _request


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def compare(expected, actual, path="result"):
    if isinstance(expected, bool) or expected is None or isinstance(expected, str):
        if type(actual) is not type(expected) or actual != expected:
            raise ValueError(f"{path}: identity differs")
    elif isinstance(expected, (int, float)):
        if (isinstance(actual, bool) or not isinstance(actual, (int, float))
                or not math.isfinite(expected) or not math.isfinite(actual)
                or not math.isclose(expected, actual, rel_tol=1e-10, abs_tol=1e-10)):
            raise ValueError(f"{path}: nonfinite or field difference exceeds 1e-10")
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise ValueError(f"{path}: field shape differs")
        for index, (a, b) in enumerate(zip(expected, actual)):
            compare(a, b, f"{path}[{index}]")
    elif isinstance(expected, dict):
        if not isinstance(actual, dict) or set(actual) != set(expected):
            raise ValueError(f"{path}: field keys differ")
        for key in expected:
            compare(expected[key], actual[key], f"{path}.{key}")
    else:
        raise ValueError(f"{path}: unsupported reference value")


def verify(worker, reference, output):
    verifier_hash = digest(Path(__file__))
    report_path = reference / "report.json"
    report_hash = digest(report_path)
    reference_report = json.loads(report_path.read_text(encoding="utf-8"))
    families = reference_report["families"]
    if (reference_report.get("status") != "passed"
            or reference_report.get("sources_unchanged") is not True
            or reference_report.get("production_qualified") is not False
            or reference_report.get("gates") != {
                "minimum_order": .8, "maximum_finest_relative_rise_l2": .05}
            or set(families) != {"conduction_limit", "tangential_shear"}):
        raise ValueError("Reference must pass the unchanged analytical refinement gates")
    for family in families.values():
        if (family.get("passed") is not True
                or [row["n"] for row in family["levels"]] != [1, 2, 4]
                or len(family["observed_orders"]) != 2
                or not all(math.isfinite(v) and v >= .8 for v in family["observed_orders"])
                or not 0 <= family["levels"][-1]["relative_rise_l2_error"] <= .05):
            raise ValueError("Reference family does not pass refinement")
    worker_hash = digest(worker)
    output.mkdir(parents=True, exist_ok=False)
    cases = []
    reference_hashes = {}
    for family in sorted(families):
        for level in (1, 2, 4):
            names = [f"{prefix}-{family}-n{level}.json" for prefix in ("request", "result")]
            paths = [reference / name for name in names]
            for name, path in zip(names, paths):
                if digest(path) != reference_report["artifacts_sha256"][name]:
                    raise ValueError("Reference artifact digest differs: " + name)
                reference_hashes[path] = reference_report["artifacts_sha256"][name]
            raw, expected = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
            actual = _request(worker, "run_em_network_resistor_cht", {"request": raw})["result"]
            for key in ("contract", "model_status", "production_qualified", "input_digest_sha256",
                        "mesh_digest_sha256", "cell_power_w", "deposited_series_resistor_power_w",
                        "outside_series_resistor_power_w", "unclassified_em_network_power_w"):
                compare(expected[key], actual[key], key)
            if actual["production_qualified"] is not False or actual["cht"]["status"] != "completed":
                raise ValueError("Frozen result was promoted or did not complete")
            compare(expected["ac"]["samples"], actual["ac"]["samples"], "ac.samples")
            compare(expected["cht"]["fields"], actual["cht"]["fields"], "cht.fields")
            energy = actual["cht"]["diagnostics"]["energy"]
            if not all(not isinstance(energy[key], bool)
                       and isinstance(energy[key], (int, float))
                       and math.isfinite(energy[key]) and 0 <= energy[key] <= 1e-9 for key in (
                    "cell_energy_relative_defect", "global_energy_relative_defect")):
                raise ValueError("Frozen energy conservation gate failed")
            saved = output / names[1]
            saved.write_text(json.dumps(actual, indent=2, allow_nan=False)+"\n", encoding="utf-8")
            cases.append({"family": family, "n": level, "status": "passed",
                          "request_sha256": reference_hashes[paths[0]], "result_sha256": digest(saved)})
    if (digest(Path(__file__)) != verifier_hash or digest(worker) != worker_hash or digest(report_path) != report_hash
            or any(digest(path) != expected for path, expected in reference_hashes.items())):
        raise ValueError("Worker or reference artifacts changed during verification")
    result = {"status": "passed", "production_qualified": False,
              "scope": __doc__.strip(), "worker_sha256": worker_hash,
              "verifier_sha256": verifier_hash,
              "reference_report_sha256": report_hash, "cases": cases,
              "field_relative_tolerance": 1e-10, "field_absolute_tolerance": 1e-10}
    (output / "report.json").write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("worker", type=Path)
    parser.add_argument("reference", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.worker.resolve(), args.reference.resolve(), args.output.resolve())))
