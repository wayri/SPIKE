# SPDX-License-Identifier: Apache-2.0
"""Package retained EMerge evidence; no engine import, solve or source rebinding.

Run with the repository Python. The fixed package epoch is reproducibility
metadata, not an execution timestamp. Historical importer differences are explicit.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from python.spike_core import __version__ as APP_VERSION
from python.spike_core.contracts import SpiDeR
from python.spike_core.extension_analysis_results import admit_analysis_result, design_binding
from python.spike_core.kicad_importer import import_kicad_design
from python.spike_core.service_project_handlers import handle_project_request
from python.spike_core.spider_v2 import SpiDeRV2

EPOCH = "1970-01-01T00:00:00.000Z"


def encode(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def load(relative: str):
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("Gallery inputs must remain inside the repository")
    return json.loads(path.read_text(encoding="utf-8"))


def digest(relative: str) -> str:
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def request(method: str, **params: object) -> dict:
    reply = handle_project_request(method, params, request_id="emerge-gallery", application_version=APP_VERSION)
    if not reply or not reply.get("ok"):
        raise ValueError(f"{method}: {reply}")
    return reply["result"]


def setup_for_ui(parameters: dict, case: dict) -> dict:
    # Older retained cases omit optional UI fields. Empty numeric strings are
    # not defaults: the frontend converts them to zero and rejects the setup.
    # Source ports, sweep and mesh inputs still come only from the retained case/config.
    defaults = {"reference_impedance_ohm": 50, "radiation_theta_step_deg": 15,
                "radiation_phi_step_deg": 15, "radiation_cut_phi_deg": 0,
                "n_workers": 2, "nearfield_z_mm": 2, "nearfield_grid_points": 11}
    values = {**defaults, **case, **parameters}
    strings = ["signal_net", "return_net", "signal_pad_id", "return_pad_id", "receive_signal_pad_id", "receive_return_pad_id",
               "frequency_start_hz", "frequency_stop_hz", "frequency_points", "mesh_resolution_mm", "reference_impedance_ohm",
               "radiation_theta_step_deg", "radiation_phi_step_deg", "radiation_cut_phi_deg", "n_workers", "nearfield_z_mm", "nearfield_grid_points"]
    setup = {key: str(values.get(key, "")) for key in strings}
    via_ids = values.get("shorting_via_ids", [])
    if (not isinstance(via_ids, list) or len(via_ids) > 16
            or any(not isinstance(item, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", item) for item in via_ids)
            or len(set(via_ids)) != len(via_ids)):
        raise ValueError("Expected at most 16 distinct bounded source shorting-via IDs")
    via_text = ", ".join(via_ids)
    if len(via_text) > 2048:
        raise ValueError("Shorting-via form text exceeds 2048 characters")
    fragmentation = values.get("fragment_copper", True)
    if not isinstance(fragmentation, bool):
        raise ValueError("fragment_copper must be a boolean")
    setup.update(shorting_via_ids=via_text, fragment_copper=fragmentation)
    setup.update(geometry_source="board", geometry_backend=values.get("geometry_backend", "emerge"),
                 python_executable="", sparse_solver=values.get("sparse_solver", "auto"), field_excited_port="1",
                 air_margin_mm="" if values.get("air_margin_mm") is None else str(values["air_margin_mm"]), radome_enabled=False)
    for key in ["include_dielectric_loss", "parallel", "nearfield_enabled"]:
        setup[key] = bool(values.get(key, False))
    surroundings = parameters.get("surrounding_geometry", {}).get("objects", [])
    if surroundings:
        if len(surroundings) != 1 or surroundings[0]["kind"] != "dielectric_box":
            raise ValueError("Only the retained single dielectric box is supported by this form")
        box = surroundings[0]
        setup.update(radome_enabled=True, **dict(zip(["radome_origin_x_mm", "radome_origin_y_mm", "radome_gap_mm"], map(str, box["origin_mm"]))),
                     **dict(zip(["radome_width_mm", "radome_depth_mm", "radome_thickness_mm"], map(str, box["size_mm"]))), radome_epsilon_r=str(box["epsilon_r"]))
    return setup


def probe_data(result: dict | None, entry: dict) -> dict:
    report = {"contract": "spike/emerge-gallery-probes/v1", "example_id": entry["id"], "result_path": entry["result_path"],
              "model_status": "unvalidated", "interpolation_performed_by_gallery": False, "samples": [],
              "recipes": ["Choose a saved frequency and receive/excited port for a complex S sample.",
                          "Select a stored angular-grid point; no angular interpolation or realized-gain inference.",
                          "For near-field planes, select a valid coordinate and inspect complex E/H components."]}
    if result is None:
        report.update(status="setup_only", recipes=["After an explicitly requested admitted two-port run, inspect S11/S21/S12/S22 at saved frequencies."])
        return report
    report.update(status="retained_result", result_sha256=digest(entry["result_path"]), analysis_id=result["analysis_id"])
    network = result["networks"]["s_parameters"]
    report["network_metadata"] = {key: value for key, value in network.items() if key != "values"}
    for index, frequency in enumerate(network["frequencies_hz"]):
        report["samples"].append({"kind": "s_parameter_matrix", "frequency_index": index, "frequency_hz": frequency,
                                  "source_pointer": f"/networks/s_parameters/values/{index}", "unit": "dimensionless_complex", "value": network["values"][index]})
    radiation = result["fields"].get("radiation", {})
    report["radiation_normalization"] = radiation.get("normalization")
    for fi, pattern in enumerate(radiation.get("patterns_3d", [])):
        index = max(range(len(pattern["relative_amplitude_db"])), key=pattern["relative_amplitude_db"].__getitem__)
        ti, pi = divmod(index, len(pattern["phi_deg"]))
        report["samples"].append({"kind": "angular_grid_sample", "frequency_index": fi, "sample_index": index,
                                  "frequency_hz": pattern["frequency_hz"], "theta_deg": pattern["theta_deg"][ti], "phi_deg": pattern["phi_deg"][pi],
                                  "source_pointer": f"/fields/radiation/patterns_3d/{fi}", "selection": "first maximum stored relative amplitude; pole azimuth is degenerate",
                                  **{key: pattern[key][index] for key in ["relative_amplitude_db", "e_theta_v_m", "e_phi_v_m"]}})
    nearfield = result["fields"].get("nearfield", {})
    report["nearfield_metadata"] = {key: value for key, value in nearfield.items() if key != "planes"}
    for pi, plane in enumerate(nearfield.get("planes", [])):
        index = next((i for i, valid in enumerate(plane["valid"]) if valid), None)
        if index is not None:
            report["samples"].append({"kind": "nearfield_coordinate_sample", "plane_index": pi, "sample_index": index,
                                      "source_pointer": f"/fields/nearfield/planes/{pi}", "selection": "first valid stored coordinate; no resampling",
                                      "frequency_hz": plane["frequency_hz"], "coordinate_mm": plane["coordinates_mm"][index],
                                      "e_v_m": plane["e_v_m"][index], "h_a_m": plane["h_a_m"][index], "valid": plane["valid"][index]})
    return report


def prepare(entry: dict) -> tuple[dict, dict, dict]:
    identifier, prefix = entry["id"], entry["id"].replace("-", "_")
    config = load(entry["config_path"])
    parameters = copy.deepcopy(config.get("parameters", config))
    parameters.pop("python_executable", None)
    inputs = set([entry["board_path"], entry["config_path"], entry["guide"], *entry["evidence_paths"]])
    result, binding = None, {"result_binding": "none_setup_only"}
    attribution = {"author": "SPIKE contributors", "license": "Apache-2.0"}
    if entry["status"] == "retained_result":
        result = load(entry["result_path"])
        base = f"examples/emerge/gui_workflow/{prefix}"
        evidence, preview = load(base + "_evidence.json"), load(base + "_preview.json")
        inputs.update([entry["result_path"], base + "_evidence.json", base + "_preview.json", base + "_result.json", base + "_simulation.py", "examples/emerge/gui_workflow/execution_manifest.json"])
        provenance = result["provenance"]
        historical = {"design_id": provenance["design_id"], "digest_sha256": provenance["design_digest_sha256"]}
        if admit_analysis_result(result, historical, extension_id="spike.emerge-suite") != result or result["model_status"] != "unvalidated":
            raise ValueError("Retained admission/status changed")
        record = next(item for item in load("examples/emerge/gui_workflow/execution_manifest.json") if item["example"] == prefix)
        if (record["result_sha256"] != digest(base + "_result.json") or record["design_binding"] != historical
                or digest(base + "_simulation.py") != provenance["generated_script_sha256"]
                or preview["script_sha256"] != provenance["generated_script_sha256"]
                or preview["case_sha256"] != provenance["board_case_sha256"]):
            raise ValueError("Retained result/script/case evidence mismatch")
        if admit_analysis_result(load(base + "_result.json"), historical, extension_id="spike.emerge-suite") != result:
            raise ValueError("Raw and admitted result differ")
        if {k: v for k, v in evidence["parameters"].items() if k != "python_executable"} != parameters:
            raise ValueError("Config differs from executed parameter evidence")
        case = preview["case"]
        if hashlib.sha256(json.dumps(case, sort_keys=True, separators=(",", ":")).encode()).hexdigest() != preview["case_sha256"]:
            raise ValueError("Preview case digest mismatch")
        binding = {"historical_binding": historical, "result_binding": "retained_historical_design_binding", "result_provenance_rewritten": False}
    else:
        case = load("examples/emerge/multilayer/case.json")
    if entry["board_path"].endswith(".kicad_pcb"):
        board_path = ROOT / entry["board_path"]
        if digest(entry["board_path"]) != evidence["board_sha256"]:
            raise ValueError("Board bytes differ from executed source evidence")
        design = json.loads(json.dumps(import_kicad_design(str(board_path)).to_dict()))
        design["source_path"] = entry["board_path"]
        design_record = {"source_file": board_path.name, "source_format": "kicad_pcb", "source_board": board_path.read_bytes().decode("utf-8")}
        binding.update(current_import_binding=design_binding(design), current_import_source_path_normalized=True, exact_historical_design_snapshot_available=False,
                       source_bytes_match_historical_evidence=True,
                       limitation="Historical importer DesignIR was not retained; unchanged source bytes and historical binding are preserved. Current importer metadata can differ.")
    else:
        design = load(entry["board_path"])
        if result is not None and design_binding(design) != binding["historical_binding"]:
            raise ValueError("Stored normalized design no longer matches result")
        canonical = SpiDeRV2.from_v1(SpiDeR(**{key: value for key, value in design.items() if key in SpiDeR.__dataclass_fields__})).to_dict()
        normalized = {"contract": "spike/design-snapshot/v1", "canonical_design": canonical, "design": design}
        design_record = {"source_file": identifier + ".spike-design.json", "source_format": "spike-normalized", "source_board": encode(normalized).decode(), "canonical_design": canonical}
        binding.update(exact_historical_design_snapshot_available=result is not None)
        if identifier == "esp32-surrogate":
            assumptions = load("examples/emerge/gui_workflow/esp32_surrogate_assumptions.json")
            original = "examples/esp32/source/iot-esp-eth-ind.kicad_pcb"
            if digest(original) != assumptions["source_board_sha256"]:
                raise ValueError("Attributed original board hash changed")
            inputs.add(original)
            attribution = {"author": "uysan", "source": "https://github.com/uysan/iot-esp-eth", "revision": "0b9eb3500cd8ccdd6193c81e1406bfe9281d88e6",
                           "license": "CERN-OHL-P-2.0", "license_text": (ROOT / "examples/esp32/source/LICENSE.md").read_text(encoding="utf-8"),
                           "assumptions": assumptions, "notice": "Derived two-conductor surrogate; not the full ESP32 board or assembly."}
    metadata = {"contract": "spike/emerge-gallery-example/v1", "id": identifier, "status": entry["status"], "guide": entry["guide"],
                "attribution": attribution, "binding_evidence": binding, "retained_parameters": parameters, "retained_case": case,
                "execution_requested": False, "production_qualified": False, "package_epoch_note": "Fixed reproducibility epoch; not a solver execution date."}
    snapshot = {"format": "spike-project-package/v2", "contract": "spike/project/v2", "saved_at": EPOCH, "project": {"id": "emerge-gallery-" + identifier, "name": entry["title"]},
                "design": design_record, "gallery": metadata,
                "analysis": {"mode": "EMI / EMC", "solver_id": "spike.emerge-suite", "view_mode": "3D", "show_axes": True,
                             "extension_workflows": {"emerge_setup": setup_for_ui(parameters, case)}, "latest_result": result,
                             "result_history": [] if result is None else [{"id": identifier, "label": entry["title"], "bundle": result}],
                             "result_display": "none" if result is None else identifier, "em_chamber_open": False,
                             "em_viewport_settings": {"visible": True, "frequencyIndex": 0, "quantity": "near_e" if identifier == "patch-fields" else "far_e",
                                                      "component": "norm", "projection": "magnitude", "style": "surface", "opacity": 0.45,
                                                      "showStructure": True, "displayRadiusMm": 40, "selectedSample": 0}},
                "workspace": {"contract": "spike/workspace-state/v1", "viewMode": "3D", "docks": {"leftOpen": True, "rightOpen": True,
                              "bottomOpen": True, "sidePanelsPinned": False, "bottomPinned": False, "leftWidthPx": 240, "rightWidthPx": 360,
                              "bottomHeightPx": 180, "activeBottomDock": "Probe table"}, "viewports": {}}, "probes": []}
    record = {"id": identifier, "status": entry["status"], "model_status": "unvalidated", "binding_evidence": binding,
              "inputs": [{"path": path, "sha256": digest(path)} for path in sorted(inputs)]}
    return snapshot, probe_data(result, entry), record


def build(output: Path = HERE) -> dict:
    catalog = load("examples/emerge/gallery/catalog.json")
    records = []
    for entry in catalog["examples"]:
        snapshot, probes, record = prepare(entry)
        for folder in ("projects", "snapshots", "probes"):
            (output / folder).mkdir(parents=True, exist_ok=True)
        path = output / "projects" / (entry["id"] + ".spike")
        request("write_project_package", path=str(path), snapshot=snapshot, generate_geometry_tables=False)
        reopened = request("read_project_package", path=str(path))
        if reopened["manifest"]["format"] != "spike-project-package/v3":
            raise ValueError("Expected canonical v3 package")
        restored = reopened["project"]
        for field in ("latest_result", "result_history", "result_display", "extension_workflows", "em_viewport_settings"):
            if restored["analysis"][field] != snapshot["analysis"][field]:
                raise ValueError(f"Roundtrip changed analysis.{field}")
        if restored["design"]["source_board"] != snapshot["design"]["source_board"]:
            raise ValueError("Roundtrip changed embedded source")
        if restored["gallery"] != snapshot["gallery"] or restored["workspace"] != snapshot["workspace"]:
            raise ValueError("Roundtrip changed gallery attribution or workspace settings")
        for folder, value in [("snapshots", snapshot), ("probes", probes)]:
            (output / folder / (entry["id"] + ".json")).write_bytes(encode(value))
        record.update(roundtrip="passed", package_format=reopened["manifest"]["format"],
                      artifacts=[{"path": entry[key], "sha256": hashlib.sha256((output / folder / (entry["id"] + suffix)).read_bytes()).hexdigest()}
                                 for key, folder, suffix in [("project_path", "projects", ".spike"), ("snapshot_path", "snapshots", ".json"), ("probe_path", "probes", ".json")]])
        records.append(record)
    manifest = {"contract": "spike/emerge-gallery-build/v1", "application_version": APP_VERSION, "solver_executed": False, "package_epoch": EPOCH,
                "builder_path": "examples/emerge/gallery/build.py", "builder_sha256": digest("examples/emerge/gallery/build.py"),
                "catalog_sha256": digest("examples/emerge/gallery/catalog.json"), "examples": records, "omissions": catalog["omissions"]}
    (output / "manifest.json").write_bytes(encode(manifest))
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE)
    report = build(parser.parse_args().output)
    print(json.dumps({"examples": len(report["examples"]), "roundtrips": [row["roundtrip"] for row in report["examples"]], "solver_executed": False}))
