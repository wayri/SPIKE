# SPDX-License-Identifier: Apache-2.0
"""Native-executable, exact-identity manufacturer approximations.

This module does not import, translate, or relabel vendor model bodies.  Its
small recipes are independently authored from selected values in official data
sheets and remain explicitly unqualified.  Discovery entries without a record
in the separate executable catalog stay non-executable.
"""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re

from .manufacturer_discovery import load_catalog as load_discovery_catalog
from .resources import resource_dir


CONTRACT = "spikes/manufacturer-executable/v1"
CATALOG_FILENAME = "manufacturer-executable-v1.json"
MODEL_STATUS = "part_specific_approximation_unqualified"
BACKEND = "native"
_KINDS = {
    "dual_opamp_one_pole_rail_clamped",
    "instrumentation_amplifier_gain_resistor",
    "npn_ebers_moll_reduced",
    "nmos_level1_source_tied_bulk",
    "shockley_two_point_upper_curve",
}
_ANALYSES = {"op", "transient_backward_euler", "transient_bdf2"}
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")


class ManufacturerExecutableError(ValueError):
    """Invalid executable-approximation catalog or operation."""


class ExecutableModelUnavailableError(ManufacturerExecutableError):
    """The discovery identity has no bundled executable approximation."""


def _finite_positive(value, label, *, zero=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ManufacturerExecutableError(label + " must be a finite number")
    invalid = value < 0 if zero else value <= 0
    if invalid:
        raise ManufacturerExecutableError(label + (" must be nonnegative" if zero else " must be positive"))


def _catalog_path() -> Path:
    return resource_dir("library") / CATALOG_FILENAME


def _discovery_index():
    return {row["id"]: row for row in load_discovery_catalog()["records"]}


def validate_record(record, discovery=None):
    if not isinstance(record, dict):
        raise ManufacturerExecutableError("Executable manufacturer record must be an object")
    required = {
        "discovery_id", "manufacturer", "part_number", "category", "model_status",
        "backend", "qualified", "pins", "model", "source", "derivation",
        "validity", "license",
    }
    if set(record) != required:
        raise ManufacturerExecutableError("Executable manufacturer record fields are incomplete")
    discovery = _discovery_index() if discovery is None else discovery
    linked = discovery.get(record["discovery_id"])
    if linked is None:
        raise ManufacturerExecutableError("Executable record is not linked to manufacturer discovery")
    for target, source in (("manufacturer", "manufacturer"), ("part_number", "part_number"), ("category", "category")):
        if record[target] != linked[source]:
            raise ManufacturerExecutableError("Executable identity differs from discovery: " + target)
    if record["model_status"] != MODEL_STATUS or record["backend"] != BACKEND or record["qualified"] is not False:
        raise ManufacturerExecutableError("Executable approximations must remain native, unqualified, and false-qualified")
    pins = record["pins"]
    if not isinstance(pins, list) or not 2 <= len(pins) <= 16:
        raise ManufacturerExecutableError("Executable approximation requires 2..16 package pins")
    numbers, names = [], []
    for pin in pins:
        if not isinstance(pin, dict) or set(pin) != {"number", "name", "role"}:
            raise ManufacturerExecutableError("Package pins require number, name, and role")
        if not all(isinstance(pin[key], str) and pin[key] for key in pin):
            raise ManufacturerExecutableError("Package pin fields must be nonempty text")
        if _IDENTIFIER.fullmatch(pin["name"]) is None:
            raise ManufacturerExecutableError("Package pin name is not a native identifier")
        numbers.append(pin["number"]); names.append(pin["name"])
    if len(set(numbers)) != len(numbers) or len(set(names)) != len(names):
        raise ManufacturerExecutableError("Package pin numbers and names must be unique")
    model = record["model"]
    if not isinstance(model, dict) or set(model) != {"kind", "parameters"} or model["kind"] not in _KINDS:
        raise ManufacturerExecutableError("Unknown executable approximation recipe")
    parameters = model["parameters"]
    if not isinstance(parameters, dict) or not parameters:
        raise ManufacturerExecutableError("Executable approximation parameters are required")
    for key, value in parameters.items():
        _finite_positive(value, key, zero=key in {
            "reverse_transit_time_s", "channel_length_modulation_per_v",
        })
    source = record["source"]
    source_fields = {"url", "document", "revision", "reviewed_on", "sections", "fields"}
    if not isinstance(source, dict) or set(source) != source_fields or not source["url"].startswith("https://"):
        raise ManufacturerExecutableError("Official HTTPS source evidence is incomplete")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", source["reviewed_on"]):
        raise ManufacturerExecutableError("Source review date must use YYYY-MM-DD")
    for field in ("document", "revision"):
        if not isinstance(source[field], str) or not source[field]:
            raise ManufacturerExecutableError("Source document identity is required")
    for field in ("sections", "fields", "derivation"):
        value = source[field] if field in source else record[field]
        if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item for item in value):
            raise ManufacturerExecutableError(field + " must be a nonempty text list")
    validity = record["validity"]
    if not isinstance(validity, dict) or set(validity) != {"analyses", "operating_conditions", "limitations"}:
        raise ManufacturerExecutableError("Validity evidence is incomplete")
    if not isinstance(validity["analyses"], list) or not validity["analyses"] or set(validity["analyses"]) - _ANALYSES:
        raise ManufacturerExecutableError("Unsupported native analysis claim")
    if not isinstance(validity["operating_conditions"], str) or not validity["operating_conditions"]:
        raise ManufacturerExecutableError("Operating conditions are required")
    if not isinstance(validity["limitations"], list) or not validity["limitations"]:
        raise ManufacturerExecutableError("Model limitations are required")
    if not isinstance(record["license"], str) or "no " not in record["license"].casefold() or "model body" not in record["license"].casefold():
        raise ManufacturerExecutableError("Clean-room model-body boundary must be explicit")
    return record


def validate_catalog(payload):
    if not isinstance(payload, dict) or payload.get("contract") != CONTRACT:
        raise ManufacturerExecutableError("Not a manufacturer executable v1 catalog")
    if set(payload) != {"contract", "version", "generated_on", "scope", "limitations", "records"}:
        raise ManufacturerExecutableError("Unexpected manufacturer executable catalog fields")
    for field in ("version", "scope", "limitations"):
        if not isinstance(payload[field], str) or not payload[field]:
            raise ManufacturerExecutableError("Catalog metadata is incomplete")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", payload["generated_on"]):
        raise ManufacturerExecutableError("Catalog generation date must use YYYY-MM-DD")
    rows = payload["records"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 208:
        raise ManufacturerExecutableError("Executable catalog must contain 1..208 records")
    discovery = _discovery_index()
    ids = set()
    for record in rows:
        validate_record(record, discovery)
        if record["discovery_id"] in ids:
            raise ManufacturerExecutableError("Duplicate executable discovery identity")
        ids.add(record["discovery_id"])
    return payload


@lru_cache(maxsize=4)
def _load_cached(path_text):
    path = Path(path_text)
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ManufacturerExecutableError("Manufacturer executable catalog exceeds 4 MiB")
    return validate_catalog(json.loads(path.read_text(encoding="utf-8")))


def load_catalog(path=None):
    """Load a detached executable catalog; no discovery row is promoted."""
    chosen = Path(path).resolve() if path is not None else _catalog_path().resolve()
    return deepcopy(_load_cached(str(chosen)))


def executable_record(discovery_id, records=None):
    if not isinstance(discovery_id, str) or not discovery_id:
        raise ManufacturerExecutableError("Manufacturer discovery ID is required")
    rows = load_catalog()["records"] if records is None else records
    matches = [row for row in rows if row["discovery_id"] == discovery_id]
    if len(matches) != 1:
        raise ExecutableModelUnavailableError(
            discovery_id + " has no bundled native executable approximation; its discovery status is unchanged"
        )
    return deepcopy(matches[0])


def availability(discovery_id):
    """Return an explicit UI-facing state for any discovery identity."""
    discovery = _discovery_index()
    if discovery_id not in discovery:
        raise ManufacturerExecutableError("Unknown manufacturer discovery identity")
    try:
        row = executable_record(discovery_id)
    except ExecutableModelUnavailableError:
        return {
            "discovery_id": discovery_id,
            "executable": False,
            "backend": None,
            "model_status": discovery[discovery_id]["model_status"],
            "qualified": False,
            "reason": "No reviewed SPIKE executable approximation is bundled for this identity.",
        }
    return {
        "discovery_id": discovery_id,
        "executable": True,
        "backend": row["backend"],
        "model_status": row["model_status"],
        "qualified": False,
        "reason": "Native part-specific approximation; not a vendor model or manufacturer qualification.",
    }


def source_pins(record_or_id):
    record = executable_record(record_or_id) if isinstance(record_or_id, str) else deepcopy(record_or_id)
    validate_record(record)
    return [pin["name"] for pin in record["pins"]]


def _fmt(value):
    return format(float(value), ".17g")


def _model_name(record):
    name = "SPK_MFG_" + re.sub(r"[^A-Za-z0-9_]", "_", record["discovery_id"])
    if _IDENTIFIER.fullmatch(name) is None:
        raise ManufacturerExecutableError("Generated manufacturer model name is invalid")
    return name


def _opamp_channel(lines, tag, plus, minus, output, vminus, vplus, p, reference="0"):
    a0 = p["open_loop_gain"]
    capacitance = a0 / (2.0 * math.pi * p["gain_bandwidth_hz"] * p["dominant_resistance_ohm"])
    drop = p["nominal_clamp_drop_v"]
    lines.extend((
        f"E{tag}_ERR {tag}_ERR {reference} {plus} {minus} {_fmt(a0)}",
        f"R{tag}_DOM {tag}_ERR {tag}_DOM {_fmt(p['dominant_resistance_ohm'])}",
        f"C{tag}_DOM {tag}_DOM {reference} {_fmt(capacitance)}",
        f"E{tag}_BUF {tag}_RAW {reference} {tag}_DOM {reference} 1",
        f"R{tag}_OUT {tag}_RAW {output} {_fmt(p['output_resistance_ohm'])}",
        f"V{tag}_HI {vplus} {tag}_HI {_fmt(p['positive_headroom_v'] + drop)}",
        f"V{tag}_LO {tag}_LO {vminus} {_fmt(p['negative_headroom_v'] + drop)}",
        f"D{tag}_HI {output} {tag}_HI CLAMP",
        f"D{tag}_LO {tag}_LO {output} CLAMP",
    ))


def native_recipe(record_or_id):
    """Return an inert native subcircuit for one reviewed approximation."""
    record = executable_record(record_or_id) if isinstance(record_or_id, str) else deepcopy(record_or_id)
    validate_record(record)
    name = _model_name(record)
    pins = source_pins(record)
    kind = record["model"]["kind"]
    p = record["model"]["parameters"]
    lines = [
        "* Original SPIKE part-specific approximation; not a vendor model or qualification",
        f".subckt {name} {' '.join(pins)}",
    ]
    if kind == "dual_opamp_one_pole_rail_clamped":
        lines.append(f".model CLAMP D(IS={_fmt(p['clamp_saturation_current_a'])} N={_fmt(p['clamp_emission_coefficient'])})")
        _opamp_channel(lines, "A", "IN_A_PLUS", "IN_A_MINUS", "OUT_A", "V_MINUS", "V_PLUS", p)
        _opamp_channel(lines, "B", "IN_B_PLUS", "IN_B_MINUS", "OUT_B", "V_MINUS", "V_PLUS", p)
    elif kind == "instrumentation_amplifier_gain_resistor":
        capacitance = 1.0 / (2.0 * math.pi * p["unity_bandwidth_hz"] * p["dominant_resistance_ohm"])
        drop = p["nominal_clamp_drop_v"]
        lines.extend((
            f".model CLAMP D(IS={_fmt(p['clamp_saturation_current_a'])} N={_fmt(p['clamp_emission_coefficient'])})",
            f"RRG1 RG1 REF {_fmt(p['rg_bias_resistance_ohm'])}",
            f"RRG2 RG2 REF {_fmt(p['rg_bias_resistance_ohm'])}",
            "EDIFF RG1 RG2 IN_PLUS IN_MINUS 1",
            f"HGAIN NGAIN REF EDIFF -{_fmt(p['gain_resistance_ohm'])}",
            "EBASE NSUM NGAIN IN_PLUS IN_MINUS 1",
            f"RDOM NSUM NDOM {_fmt(p['dominant_resistance_ohm'])}",
            f"CDOM NDOM REF {_fmt(capacitance)}",
            "EBUF NRAW REF NDOM REF 1",
            f"ROUT NRAW OUT {_fmt(p['output_resistance_ohm'])}",
            f"VHI V_PLUS NHI {_fmt(p['positive_headroom_v'] + drop)}",
            f"VLO NLO V_MINUS {_fmt(p['negative_headroom_v'] + drop)}",
            "DHI OUT NHI CLAMP",
            "DLO NLO OUT CLAMP",
        ))
    elif kind == "npn_ebers_moll_reduced":
        lines.extend((
            ".model CORE NPN(" + " ".join((
                "IS=" + _fmt(p["saturation_current_a"]),
                "BF=" + _fmt(p["forward_beta"]),
                "BR=" + _fmt(p["reverse_beta"]),
                "NF=" + _fmt(p["emission_coefficient"]),
                "CBE=" + _fmt(p["base_emitter_capacitance_f"]),
                "CBC=" + _fmt(p["base_collector_capacitance_f"]),
                "TF=" + _fmt(p["forward_transit_time_s"]),
                "TR=" + _fmt(p["reverse_transit_time_s"]),
            )) + ")",
            "QCORE C B E CORE",
        ))
    elif kind == "nmos_level1_source_tied_bulk":
        lines.extend((
            ".model CORE NMOS(" + " ".join((
                "LEVEL=1",
                "VTO=" + _fmt(p["threshold_voltage_v"]),
                "KP=" + _fmt(p["transconductance_a_per_v2"]),
                "LAMBDA=" + _fmt(p["channel_length_modulation_per_v"]),
                "GAMMA=0 PHI=0.6",
                "CGS=" + _fmt(p["gate_source_capacitance_f"]),
                "CGD=" + _fmt(p["gate_drain_capacitance_f"]),
                "CDS=" + _fmt(p["drain_source_capacitance_f"]),
            )) + ")",
            f".model BODY D(IS={_fmt(p['body_diode_saturation_current_a'])} N={_fmt(p['body_diode_emission_coefficient'])})",
            "MCORE D G S S CORE W=1 L=1",
            "DBODY S D BODY",
        ))
    else:
        lines.extend((
            f".model CORE D(IS={_fmt(p['saturation_current_a'])} N={_fmt(p['emission_coefficient'])} TNOM={_fmt(p['temperature_k'] - 273.15)})",
            "DCORE A K CORE",
        ))
    lines.append(f".ends {name}")
    return {
        "name": name,
        "pins": pins,
        "source": "\n".join(lines) + "\n",
        "backend": BACKEND,
        "model_status": MODEL_STATUS,
        "qualified": False,
        "discovery_id": record["discovery_id"],
    }


def as_component_record(record_or_id):
    """Adapt one record for the manufacturer browser without claiming qualification."""
    record = executable_record(record_or_id) if isinstance(record_or_id, str) else deepcopy(record_or_id)
    validate_record(record)
    return {
        "id": "manufacturer-executable." + record["discovery_id"],
        "category": "Manufacturer executable approximations",
        "family": record["model"]["kind"],
        "name": record["manufacturer"] + " " + record["part_number"],
        "status": "native_subcircuit",
        "model_status": MODEL_STATUS,
        "backend": BACKEND,
        "manufacturer": record["manufacturer"],
        "exact_mpn": record["part_number"],
        "qualification": "not_manufacturer_qualified",
        "qualified": False,
        "source_url": record["source"]["url"],
        "source_pins": source_pins(record),
        "limitations": " ".join(record["validity"]["limitations"]),
    }


def _generated_state(document_source, generated_source, name):
    pattern = re.compile(r"(?ims)^\s*\.subckt\s+" + re.escape(name) + r"\b.*?^\s*\.ends(?:\s+" + re.escape(name) + r")?\s*$")
    existing = pattern.findall(document_source)
    if not existing:
        return "absent"
    expected = pattern.findall(generated_source)
    if len(existing) != 1 or len(expected) != 1 or existing[0].strip() != expected[0].strip():
        raise ManufacturerExecutableError("Existing generated manufacturer model is edited or duplicated")
    return "exact"


def prepare_install(document, record_or_id, mapping, *, count=1, x=140, y=180, spacing=240):
    """Build an atomic native insertion plan without mutating ``document``."""
    from .document import Document

    record = executable_record(record_or_id) if isinstance(record_or_id, str) else deepcopy(record_or_id)
    validate_record(record)
    recipe = native_recipe(record)
    if type(count) is not int or not 1 <= count <= 100:
        raise ManufacturerExecutableError("Insert count must be 1..100")
    if not isinstance(mapping, dict) or set(mapping) != set(recipe["pins"]):
        raise ManufacturerExecutableError("Map every package pin exactly once")
    for node in mapping.values():
        if not isinstance(node, str) or re.fullmatch(r"[A-Za-z0-9_.$:/+-]{1,128}", node.replace("{n}", "1")) is None:
            raise ManufacturerExecutableError("Invalid mapped node name")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in (x, y, spacing)) or spacing < 100:
        raise ManufacturerExecutableError("Invalid canvas placement")
    digest = hashlib.sha256(recipe["source"].encode("utf-8")).hexdigest()
    model_name = recipe["name"] + "_" + digest[:12]
    generated = recipe["source"].replace(recipe["name"], model_name)
    state = _generated_state(document.data["source"], generated, model_name)
    insertion = "" if state == "exact" else generated
    occupied = {match.upper() for match in re.findall(r"(?im)^\s*(XMAN\d+)\s", document.data["source"])}
    refs, number = [], 1
    for index in range(count):
        while "XMAN" + str(number) in occupied:
            number += 1
        ref = "XMAN" + str(number)
        refs.append(ref); occupied.add(ref)
        nodes = [mapping[pin].replace("{n}", str(index + 1)) for pin in recipe["pins"]]
        insertion += ref + " " + " ".join(nodes) + " " + model_name + "\n"
    source = document.data["source"]
    changed = re.sub(r"(?im)^\s*\.end\s*$", lambda match: insertion + ".end", source)
    if changed == source:
        changed = source.rstrip() + "\n" + insertion + ".end\n"
    candidate = Document(document.data)
    candidate.apply_source(changed)
    groups = {ref: [] for ref in refs}
    for part in candidate.data["components"]:
        top = part["ref"].split(":", 1)[0].upper()
        if top in groups:
            groups[top].append(part)
    if any(not parts for parts in groups.values()):
        raise ManufacturerExecutableError("Inserted manufacturer model did not flatten into native parts")
    columns = max(1, min(4, 1000 // max(int(spacing), 300)))
    evidence = (
        record["manufacturer"] + " " + record["part_number"] + ": " + MODEL_STATUS
        + "; native SPIKE reduction, not a vendor model or manufacturer qualification. "
        + record["source"]["url"]
    )
    marker = {
        "discovery_id": record["discovery_id"],
        "manufacturer": record["manufacturer"],
        "part_number": record["part_number"],
        "model_status": MODEL_STATUS,
        "qualified": False,
        "source_url": record["source"]["url"],
    }
    for index, ref in enumerate(refs):
        for offset, part in enumerate(groups[ref]):
            part["x"] = x + (index % columns) * max(spacing, 300) + (offset % 2) * 140
            part["y"] = y + (index // columns) * (220 + 70 * len(groups[ref])) + (offset // 2) * 120
            part["parameters"]["manufacturer_executable"] = deepcopy(marker)
            part["evidence"] = evidence
    return {
        "source": candidate.data["source"],
        "components": candidate.data["components"],
        "title": candidate.data["title"],
        "refs": refs,
        "model": model_name,
        "manufacturer_executable": {
            "record": deepcopy(record),
            "compiled_source_sha256": digest,
            "pins": list(recipe["pins"]),
            "model_status": MODEL_STATUS,
            "qualified": False,
        },
    }


def install(document, record_or_id, mapping, *, count=1, x=140, y=180, spacing=240):
    """Atomically install an executable approximation into a Studio document."""
    plan = prepare_install(document, record_or_id, mapping, count=count, x=x, y=y, spacing=spacing)

    def mutate(data):
        for key in ("source", "components", "title"):
            data[key] = deepcopy(plan[key])
        models = data["metadata"].setdefault("manufacturer_executable_models", {})
        models[plan["model"]] = deepcopy(plan["manufacturer_executable"])
        recent = data["metadata"].setdefault("library_browser", {}).setdefault("recent", [])
        ident = "manufacturer-executable." + plan["manufacturer_executable"]["record"]["discovery_id"]
        data["metadata"]["library_browser"]["recent"] = [ident] + [item for item in recent if item != ident][:49]

    document.commit(mutate)
    return plan


def format_record(record_or_id):
    record = executable_record(record_or_id) if isinstance(record_or_id, str) else deepcopy(record_or_id)
    validate_record(record)
    pin_text = ", ".join(pin["number"] + "=" + pin["name"] for pin in record["pins"])
    return (
        f"{record['manufacturer']} {record['part_number']}\n"
        f"Model status: {record['model_status']}\nBackend: native\nQualified: false\n"
        f"Pins: {pin_text}\nValid use: {record['validity']['operating_conditions']}\n"
        f"Limitations: {' '.join(record['validity']['limitations'])}\n"
        f"Official source: {record['source']['url']}\n"
        "This is an original SPIKE reduction, not a redistributed vendor model."
    )


__all__ = [
    "BACKEND", "CATALOG_FILENAME", "CONTRACT", "MODEL_STATUS",
    "ExecutableModelUnavailableError", "ManufacturerExecutableError",
    "as_component_record", "availability", "executable_record", "format_record",
    "install", "load_catalog", "native_recipe", "prepare_install", "source_pins",
    "validate_catalog", "validate_record",
]
