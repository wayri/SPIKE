# SPDX-License-Identifier: Apache-2.0
"""Focused exact-MPN catalog with fail-closed circuit installation.

The bundled JSON contains selected factual fields transcribed from official
manufacturer pages.  It does not redistribute manufacturer simulation models
or claim to cover every manufacturer.  Only resistor and capacitor records
with an explicit ideal-nominal recipe can be inserted without a separately
reviewed vendor model.
"""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import json
import math
from pathlib import Path
import re
from urllib.parse import urlparse

from .resources import resource_dir
from .fuzzy_search import ranked


CONTRACT = "spikes/manufacturer-parts/v1"
CATALOG_FILENAME = "manufacturer-parts-v1.json"
PLACEABLE_KINDS = {"ideal_nominal_resistor", "ideal_nominal_capacitor", "ideal_nominal_inductor"}
READINESS = {"placeable_ideal_nominal", "vendor_model_required"}
ALLOWED_UNITS = {
    "1", "A", "A2 s", "count", "F", "Hz", "K", "K/W", "m", "nm",
    "ohm", "percent", "s", "V", "VDC", "VAC", "W", "degree C", "H",
}


class ManufacturerPartError(ValueError):
    """Invalid catalog data or requested catalog operation."""


class ModelUnavailableError(ManufacturerPartError):
    """The selected exact MPN has no executable model in this catalog."""


def _catalog_path() -> Path:
    return resource_dir("library") / CATALOG_FILENAME


def _finite_number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ManufacturerPartError(f"{label} must be a finite number")


def validate_record(record):
    if not isinstance(record, dict):
        raise ManufacturerPartError("Manufacturer record must be an object")
    required = {
        "id", "manufacturer", "mpn", "category", "description", "nominal",
        "tolerance", "ratings", "package", "pins", "model", "source",
    }
    missing = required - set(record)
    if missing:
        raise ManufacturerPartError("Missing manufacturer fields: " + ", ".join(sorted(missing)))
    if not re.fullmatch(r"[a-z0-9_.-]{3,128}", record["id"]):
        raise ManufacturerPartError("Invalid manufacturer record ID")
    for field in ("manufacturer", "mpn", "category", "description", "package"):
        if not isinstance(record[field], str) or not record[field].strip() or len(record[field]) > 512:
            raise ManufacturerPartError(f"Invalid {field}")
    nominal = record["nominal"]
    if not isinstance(nominal, dict) or set(nominal) != {"value", "unit", "label"}:
        raise ManufacturerPartError("Nominal must contain value, unit and label")
    _finite_number(nominal["value"], "Nominal value")
    if nominal["unit"] not in ALLOWED_UNITS:
        raise ManufacturerPartError("Unsupported nominal unit")
    tolerance = record["tolerance"]
    if not isinstance(tolerance, dict) or tolerance.get("kind") not in {"symmetric", "not_applicable"}:
        raise ManufacturerPartError("Tolerance must be symmetric or not_applicable")
    if tolerance["kind"] == "symmetric":
        if set(tolerance) != {"kind", "value", "unit", "display"}:
            raise ManufacturerPartError("Symmetric tolerance fields are incomplete")
        _finite_number(tolerance["value"], "Tolerance")
        if tolerance["value"] < 0 or tolerance["unit"] not in {"percent", "F", "ohm"}:
            raise ManufacturerPartError("Invalid symmetric tolerance")
    elif set(tolerance) != {"kind", "display"}:
        raise ManufacturerPartError("not_applicable tolerance must explain itself")
    if not isinstance(record["ratings"], list) or not record["ratings"]:
        raise ManufacturerPartError("At least one sourced rating is required")
    for rating in record["ratings"]:
        if not isinstance(rating, dict) or set(rating) - {"name", "value", "unit", "condition", "qualifier"}:
            raise ManufacturerPartError("Invalid rating fields")
        if not isinstance(rating.get("name"), str) or not rating["name"]:
            raise ManufacturerPartError("Rating name is required")
        value = rating.get("value")
        values = value if isinstance(value, list) else [value]
        if not values:
            raise ManufacturerPartError("Rating value is required")
        for item in values:
            _finite_number(item, "Rating value")
        if rating.get("unit") not in ALLOWED_UNITS:
            raise ManufacturerPartError("Unsupported rating unit")
    if not isinstance(record["pins"], list) or len(record["pins"]) < 2 or len(record["pins"]) > 64:
        raise ManufacturerPartError("A bounded pin inventory is required")
    numbers = []
    for pin in record["pins"]:
        if not isinstance(pin, dict) or set(pin) != {"number", "name", "role"}:
            raise ManufacturerPartError("Pins require number, name and role")
        if any(not isinstance(pin[key], str) or not pin[key].strip() for key in pin):
            raise ManufacturerPartError("Pin fields must be non-empty text")
        numbers.append(pin["number"])
    if len(numbers) != len(set(numbers)):
        raise ManufacturerPartError("Pin numbers must be unique")
    model = record["model"]
    if not isinstance(model, dict) or set(model) != {"kind", "readiness", "limitations"}:
        raise ManufacturerPartError("Model metadata is incomplete")
    if model["readiness"] not in READINESS:
        raise ManufacturerPartError("Unknown model readiness")
    if (model["kind"] in PLACEABLE_KINDS) != (model["readiness"] == "placeable_ideal_nominal"):
        raise ManufacturerPartError("Model kind/readiness mismatch")
    if model["kind"] == "ideal_nominal_resistor" and (record["category"] != "resistor" or nominal["unit"] != "ohm"):
        raise ManufacturerPartError("Resistor recipe requires an ohm nominal")
    if model["kind"] == "ideal_nominal_capacitor" and (record["category"] != "capacitor" or nominal["unit"] != "F"):
        raise ManufacturerPartError("Capacitor recipe requires a farad nominal")
    if model['kind']=='ideal_nominal_inductor' and (record['category']!='inductor' or nominal['unit']!='H'):
        raise ManufacturerPartError('Inductor recipe requires a henry nominal')
    source = record["source"]
    if not isinstance(source, dict) or set(source) != {"url", "accessed_on", "document", "fields"}:
        raise ManufacturerPartError("Source metadata is incomplete")
    parsed = urlparse(source["url"])
    if parsed.scheme != "https" or not parsed.netloc:
        raise ManufacturerPartError("Source must be an HTTPS manufacturer URL")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", source["accessed_on"]):
        raise ManufacturerPartError("Source access date must use YYYY-MM-DD")
    if not isinstance(source["fields"], list) or not source["fields"]:
        raise ManufacturerPartError("Source field inventory is required")


def validate_catalog(payload):
    if not isinstance(payload, dict) or payload.get("contract") != CONTRACT:
        raise ManufacturerPartError("Not a manufacturer-parts v1 catalog")
    if set(payload) != {"contract", "version", "generated_on", "scope", "limitations", "records"}:
        raise ManufacturerPartError("Unexpected manufacturer catalog fields")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", payload["generated_on"]):
        raise ManufacturerPartError("Catalog generation date must use YYYY-MM-DD")
    if any(not isinstance(payload[field], str) or not payload[field].strip() for field in ("version", "scope", "limitations")):
        raise ManufacturerPartError("Catalog version, scope and limitations are required")
    records = payload["records"]
    if not isinstance(records, list) or not 20 <= len(records) <= 5000:
        raise ManufacturerPartError("Manufacturer catalog must contain 20..5,000 records")
    ids, mpns = set(), set()
    for record in records:
        validate_record(record)
        ident = record["id"]
        mpn = (record["manufacturer"].casefold(), record["mpn"].casefold())
        if ident in ids or mpn in mpns:
            raise ManufacturerPartError("Duplicate manufacturer record")
        ids.add(ident)
        mpns.add(mpn)
    return payload


@lru_cache(maxsize=4)
def _load_cached(path_text):
    path = Path(path_text)
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ManufacturerPartError("Manufacturer catalog exceeds 4 MiB")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return validate_catalog(payload)


def load_catalog(path=None):
    """Load and validate the bundled catalog, returning an isolated copy."""
    chosen = Path(path).resolve() if path is not None else _catalog_path().resolve()
    payload = deepcopy(_load_cached(str(chosen)))
    if path is None:
        from .standard_logic_seed import records as logic_records
        from .standard_analog_seed import records as analog_records
        from .standard_passive_seed import records as passive_records
        payload['records'].extend(logic_records())
        payload['records'].extend(analog_records())
        payload['records'].extend(passive_records())
        payload['version'] = '1.2.0'
        payload['generated_on'] = '2026-10-12'
        payload['scope'] += '; sourced HC, analog and passive package extensions; ideal nominal RLC and functional digital API, not manufacturer-qualified'
        validate_catalog(payload)
    return payload


def find_record(identifier, records=None):
    if not isinstance(identifier, str) or not identifier.strip():
        raise ManufacturerPartError("Part ID or exact MPN is required")
    rows = records if records is not None else load_catalog()["records"]
    needle = identifier.casefold()
    matches = [r for r in rows if needle in {r["id"].casefold(), r["mpn"].casefold()}]
    if len(matches) != 1:
        raise ManufacturerPartError("Exact manufacturer part was not found")
    return deepcopy(matches[0])


def query(records, text="", *, manufacturer=None, category=None, readiness=None):
    """Case-insensitive AND search over the small, local, immutable seed."""
    if not isinstance(text, str) or len(text) > 512:
        raise ManufacturerPartError("Search is limited to 512 characters")
    result = []
    for record in records:
        if manufacturer and record["manufacturer"] != manufacturer:
            continue
        if category and record["category"] != category:
            continue
        if readiness and record["model"]["readiness"] != readiness:
            continue
        searchable = " ".join((
            record["id"], record["manufacturer"], record["mpn"], record["category"],
            record["description"], record["package"], record["model"]["kind"],
        )).casefold()
        result.append(record)
    result.sort(key=lambda r:(r['manufacturer'].casefold(),r['mpn'].casefold()))
    return ranked(result,text,text=lambda r:' '.join(str(r.get(k,'')) for k in ('id','manufacturer','mpn','category','description','package'))+' '+r['model']['kind'])


def is_placeable(record):
    validate_record(record)
    return record["model"]["kind"] in PLACEABLE_KINDS


def source_pins(record):
    if not is_placeable(record):
        raise ModelUnavailableError(
            f"{record['mpn']} has no bundled executable model. Obtain the exact vendor model, "
            "preserve its license and hash, review its pins, and qualify it before placement."
        )
    return ["P", "N"]


def as_component_record(record):
    """Adapt a sourced passive to the existing ideal R/C recipe contract."""
    validate_record(record)
    pins = source_pins(record)
    kind = record["model"]["kind"]
    family,key={'ideal_nominal_resistor':('resistor','r'),'ideal_nominal_capacitor':('capacitor','c'),'ideal_nominal_inductor':('inductor','l')}[kind]
    nominal = record["nominal"]
    limitations = (
        f"Exact MPN identity and nominal metadata are sourced from {record['source']['url']}. "
        f"Circuit behavior is an SPIKES-generated ideal {family} fixed at the stated nominal; "
        "it does not enforce tolerance or ratings and does not model bias, temperature, aging, "
        "failure, package parasitics, or manufacturer precision. " + record["model"]["limitations"]
    )
    return {
        "id": "manufacturer." + record["id"],
        "category": "Passives",
        "family": family,
        "name": f"{record['manufacturer']} {record['mpn']} - {nominal['label']}",
        "parameters": {key: nominal["value"]},
        "parameter_unit": nominal["unit"],
        "status": "native_subcircuit",
        "manufacturer": record["manufacturer"],
        "fidelity": "ideal_nominal_from_sourced_part",
        "license": "Catalog facts only; generated ideal recipe is Apache-2.0. No vendor model redistributed.",
        "limitations": limitations,
        "qualification": "manufacturer_identity_sourced_model_unqualified",
        "origin": f"{record['source']['document']} accessed {record['source']['accessed_on']}",
        "exact_mpn": record["mpn"],
        "source_url": record["source"]["url"],
        "source_pins": pins,
    }


def prepare_install(document, record_or_identifier, mapping, *, count=1, x=140, y=180,primitive=False):
    """Build a checked insertion plan without mutating the document."""
    record = find_record(record_or_identifier) if isinstance(record_or_identifier, str) else deepcopy(record_or_identifier)
    component = as_component_record(record)
    from .library_browser import insertion_plan
    plan = insertion_plan(document, component, mapping, count=count, x=x, y=y,primitive=primitive)
    plan["manufacturer_part"] = {
        "id": record["id"], "manufacturer": record["manufacturer"], "mpn": record["mpn"],
        "source_url": record["source"]["url"], "model_kind": record["model"]["kind"],
    }
    for part in plan['components']:
        if part['ref'].split(':',1)[0].upper() not in plan['refs']:continue
        part['parameters']['manufacturer_part']=deepcopy(record)
        part['evidence']=('Exact manufacturer identity/nominal/ratings sourced; '
                          'ideal nominal model, not manufacturer-qualified. '+record['source']['url'])
        for rating in record['ratings']:
            if rating['name']=='rated_voltage' and rating['unit'] in ('V','VDC'):
                part['limits']['voltage_v']=rating['value']
            if rating['name']=='rated_power' and rating['unit']=='W':
                part['limits']['power_w']=rating['value']
    return plan


def install(document, record_or_identifier, mapping, *, count=1, x=140, y=180,primitive=False):
    """Atomically insert an eligible ideal-nominal passive through the existing installer."""
    plan = prepare_install(document, record_or_identifier, mapping, count=count, x=x, y=y,primitive=primitive)
    from .library_browser import apply_insertion
    apply_insertion(document, plan, "manufacturer." + plan["manufacturer_part"]["id"])
    return plan


def store_vendor_model(document, path, record_or_identifier, license_text, source_url=None):
    """Store a user-supplied model review with exact hash and license; never approve it.

    This is acquisition/review intake, not an executable install path.  Fitted or
    parser-compatible drafts remain unqualified.
    """
    record = find_record(record_or_identifier) if isinstance(record_or_identifier, str) else deepcopy(record_or_identifier)
    validate_record(record)
    if not isinstance(license_text, str) or not license_text.strip() or len(license_text) > 16384:
        raise ManufacturerPartError("User-supplied license/terms text is required (maximum 16 KiB)")
    chosen_url = source_url or record["source"]["url"]
    parsed = urlparse(chosen_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ManufacturerPartError("Vendor model source must be an HTTPS URL")
    from .vendor_intake import intake
    report = intake(path)
    report["provenance"] = {
        "manufacturer": record["manufacturer"], "part_number": record["mpn"],
        "source_url": chosen_url, "catalog_record_id": record["id"],
        "user_supplied": True,
    }
    report["license"] = {"declared_by_user": license_text.strip(), "redistribution": "not_reviewed"}
    report["execution"] = "not_approved"
    report["compatibility"] = "not_qualified"
    report["fitted_draft_status"] = "not_qualified"
    key = report["content_sha256"]
    def mutate(data):
        data["metadata"].setdefault("manufacturer_models", {})[key] = deepcopy(report)
    document.commit(mutate)
    return key


def format_record(record):
    validate_record(record)
    ratings = "\n".join(
        f"  - {r['name']}: {r['value']} {r['unit']}"
        + (f" ({r['condition']})" if r.get("condition") else "")
        + (f" [{r['qualifier']}]" if r.get("qualifier") else "")
        for r in record["ratings"]
    )
    pins = "\n".join(f"  {p['number']}: {p['name']} [{p['role']}]" for p in record["pins"])
    return (
        f"{record['manufacturer']} {record['mpn']}\n{record['description']}\n"
        f"Category: {record['category']}\nPackage: {record['package']}\n"
        f"Nominal: {record['nominal']['label']}\nTolerance: {record['tolerance']['display']}\n"
        f"Ratings (selected sourced fields):\n{ratings}\nPins:\n{pins}\n\n"
        f"Model readiness: {record['model']['readiness']}\nModel kind: {record['model']['kind']}\n"
        f"Limitations: {record['model']['limitations']}\n\n"
        f"Official source: {record['source']['url']}\nAccessed: {record['source']['accessed_on']}\n"
        "A listed rating is metadata, not an enforced simulation limit. Fitted drafts are not qualified."
    )
