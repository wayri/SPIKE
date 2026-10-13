# SPDX-License-Identifier: Apache-2.0
"""Fail-closed coverage accounting for exact-MPN active-device models.

Catalog discovery, executable solver compatibility, and engineering
qualification are deliberately separate claims.  Generic presets, helper
circuits, and repeated package rows cannot satisfy an exact-MPN target.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date
import re


CONTRACT = "spikes/active-library-coverage/v1"
EVIDENCE_CONTRACT = "spikes/active-model-evidence/v1"
LOGIC_MANIFEST_CONTRACT = "spikes/logic-54-74-manifest/v1"
TARGET_PER_CATEGORY = 100
ACTIVE_CATEGORIES = (
    "opamp", "bjt", "npn", "pnp", "mosfet", "nmos", "pmos",
    "ganfet", "sicfet", "mesfet", "pin_diode", "diode", "schottky",
    "controller", "pwm",
)

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_LOGIC_MPN = re.compile(r"^(?:SN)?(?:54|74)[A-Z0-9][A-Z0-9,./#+-]*$", re.IGNORECASE)


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def _key(record):
    manufacturer = _text(record.get("manufacturer"))
    mpn = _text(record.get("mpn") or record.get("exact_mpn"))
    if not manufacturer or not mpn:
        return None
    return manufacturer.casefold(), mpn.casefold()


def _valid_date(value):
    if not _DATE.fullmatch(_text(value)):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _discovery_evidence(record):
    """Return whether identity and provenance establish a discovered MPN."""
    if _key(record) is None:
        return False, "missing manufacturer or exact MPN"
    source = record.get("source")
    if not isinstance(source, dict):
        return False, "missing structured source evidence"
    url = _text(source.get("url"))
    fields = source.get("fields")
    if (not url.startswith("https://") or not _valid_date(source.get("accessed_on"))
            or not _text(source.get("document"))
            or not isinstance(fields, list) or not fields
            or any(not _text(item) for item in fields)):
        return False, "incomplete source URL, access date, document, or field inventory"
    return True, ""


def _evidence_stage(record, stage):
    """Validate explicit, digest-bound execution or qualification evidence."""
    evidence = record.get("coverage_evidence")
    if not isinstance(evidence, dict):
        return False, "missing coverage_evidence"
    if evidence.get("contract") != EVIDENCE_CONTRACT:
        return False, "unsupported active-model evidence contract"
    if not _SHA256.fullmatch(_text(evidence.get("model_sha256"))):
        return False, "missing model SHA-256"
    item = evidence.get(stage)
    if not isinstance(item, dict):
        return False, f"missing {stage} evidence"
    if item.get("status") != "passed":
        return False, f"{stage} status is not passed"
    required = ("artifact", "artifact_sha256", "checked_on")
    if any(not _text(item.get(field)) for field in required):
        return False, f"incomplete {stage} artifact evidence"
    if not _SHA256.fullmatch(item["artifact_sha256"]):
        return False, f"invalid {stage} artifact SHA-256"
    if not _valid_date(item["checked_on"]):
        return False, f"invalid {stage} evidence date"
    if stage == "execution" and not _text(item.get("backend")):
        return False, "execution backend is required"
    if stage == "qualification" and (
        not _text(item.get("scope")) or not _text(item.get("reviewer"))
    ):
        return False, "qualification scope and reviewer are required"
    return True, ""


def _explicit_tags(record):
    category = _text(record.get("category")).casefold().replace("-", "_").replace(" ", "_")
    family = _text(record.get("family")).casefold().replace("-", "_").replace(" ", "_")
    description = " " + _text(record.get("description")).casefold().replace("-", "_") + " "
    tags = {category, family} - {""}
    result = set()

    if tags & {"opamp", "operational_amplifier", "operational_amplifiers"}:
        result.add("opamp")
    if tags & {"bjt", "bipolar_transistor", "npn", "pnp"}:
        result.add("bjt")
    if "npn" in tags or ("bipolar_transistor" in tags and re.search(r"\bnpn\b", description)):
        result.add("npn")
    if "pnp" in tags or ("bipolar_transistor" in tags and re.search(r"\bpnp\b", description)):
        result.add("pnp")

    mos_tags = {
        "mosfet", "nmos", "pmos", "nmos_enhancement", "pmos_enhancement",
        "nmos_depletion", "ganfet", "gan_fet", "gan_channel", "sicfet",
        "sic_fet", "sic_channel",
    }
    if tags & mos_tags:
        result.add("mosfet")
    if tags & {"nmos", "nmos_enhancement", "nmos_depletion"} or (
        "mosfet" in tags and re.search(r"\bn[ _]channel\b", description)
    ):
        result.add("nmos")
    if tags & {"pmos", "pmos_enhancement"} or (
        "mosfet" in tags and re.search(r"\bp[ _]channel\b", description)
    ):
        result.add("pmos")
    if tags & {"ganfet", "gan_fet", "gan_channel"}:
        result.add("ganfet")
    if tags & {"sicfet", "sic_fet", "sic_channel"}:
        result.add("sicfet")
    if tags & {"mesfet", "mesfet_channel"}:
        result.add("mesfet")

    diode_tags = {"diode", "pin_diode", "pin_diode_rf", "schottky", "schottky_diode"}
    if tags & diode_tags:
        result.add("diode")
    if tags & {"pin_diode", "pin_diode_rf"}:
        result.add("pin_diode")
    if tags & {"schottky", "schottky_diode"}:
        result.add("schottky")

    if tags & {"controller", "controller_ic", "control_ic", "pwm_controller", "pwm_control_ic"}:
        result.add("controller")
    if tags & {"pwm", "pwm_controller", "pwm_control_ic"}:
        result.add("pwm")
    return result


def _logic_key(record):
    key = _key(record)
    if key is None:
        return None
    category = _text(record.get("category")).casefold()
    if category not in {"logic_ic", "logic", "digital_logic"}:
        return None
    return key if _LOGIC_MPN.fullmatch(_text(record.get("mpn") or record.get("exact_mpn"))) else None


def _validate_logic_manifest(manifest):
    if manifest is None:
        return None, "no authoritative 54/74 universe manifest supplied"
    if not isinstance(manifest, dict) or manifest.get("contract") != LOGIC_MANIFEST_CONTRACT:
        return None, "unsupported 54/74 universe manifest"
    source = manifest.get("source")
    expected = manifest.get("expected")
    if (not isinstance(source, dict) or not _text(source.get("url")).startswith("https://")
            or not _valid_date(source.get("accessed_on")) or not _text(source.get("document"))
            or not isinstance(expected, list) or not expected):
        return None, "54/74 manifest provenance or expected-MPN inventory is incomplete"
    keys = []
    for item in expected:
        if not isinstance(item, dict) or _key(item) is None or not _LOGIC_MPN.fullmatch(_text(item.get("mpn"))):
            return None, "54/74 manifest contains an invalid manufacturer/MPN entry"
        keys.append(_key(item))
    if len(keys) != len(set(keys)):
        return None, "54/74 manifest contains duplicate manufacturer/MPN entries"
    return set(keys), ""


def audit_active_library(records=None, *, logic_manifest=None):
    """Audit exact-MPN active-library coverage without inferring readiness.

    With no records argument, the bundled manufacturer catalog is audited.
    Unknown or malformed claims are reported and remain uncounted.
    """
    if records is None:
        from .manufacturer_parts import load_catalog
        records = load_catalog()["records"]
    if not isinstance(records, (list, tuple)):
        records = list(records)

    by_category = {name: defaultdict(set) for name in ACTIVE_CATEGORIES}
    logic = defaultdict(set)
    issues = []
    seen_rows = defaultdict(int)

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            issues.append(f"record[{index}]: record is not an object")
            continue
        key = _key(record)
        if key is not None:
            seen_rows[key] += 1
        categories = _explicit_tags(record)
        logic_key = _logic_key(record)
        if not categories and logic_key is None:
            continue

        discovered, reason = _discovery_evidence(record)
        label = f"{_text(record.get('manufacturer'))} {_text(record.get('mpn') or record.get('exact_mpn'))}".strip() or f"record[{index}]"
        if not discovered:
            issues.append(f"{label}: discovery excluded: {reason}")
            continue

        executable, execution_reason = _evidence_stage(record, "execution")
        qualified = False
        qualification_reason = "execution evidence did not pass"
        if executable:
            qualified, qualification_reason = _evidence_stage(record, "qualification")
        elif isinstance(record.get("coverage_evidence"), dict):
            issues.append(f"{label}: executable claim excluded: {execution_reason}")

        if executable and not qualified and isinstance(record.get("coverage_evidence", {}).get("qualification"), dict):
            issues.append(f"{label}: qualification claim excluded: {qualification_reason}")

        stages = ["discovered"]
        if executable:
            stages.append("executable")
        if qualified:
            stages.append("qualified")
        for category in categories:
            for stage in stages:
                by_category[category][stage].add(key)
        if logic_key is not None:
            for stage in stages:
                logic[stage].add(key)

    for key, count in sorted(seen_rows.items()):
        if count > 1:
            issues.append(f"duplicate rows collapsed for {key[0]} / {key[1]} ({count} rows)")

    categories = {}
    for name in ACTIVE_CATEGORIES:
        discovered = len(by_category[name]["discovered"])
        executable = len(by_category[name]["executable"])
        qualified = len(by_category[name]["qualified"])
        categories[name] = {
            "target": TARGET_PER_CATEGORY,
            "target_kind": "minimum_distinct_executable_mpn",
            "discovered": discovered,
            "executable": executable,
            "qualified": qualified,
            "gap": max(0, TARGET_PER_CATEGORY - executable),
            "status": "met" if executable >= TARGET_PER_CATEGORY else "not_met",
        }

    expected, manifest_problem = _validate_logic_manifest(logic_manifest)
    discovered_logic = logic["discovered"]
    executable_logic = logic["executable"]
    qualified_logic = logic["qualified"]
    logic_report = {
        "target": None,
        "target_kind": "exhaustive_authoritative_manifest",
        "discovered": len(discovered_logic),
        "executable": len(executable_logic),
        "qualified": len(qualified_logic),
        "manifest_verified": expected is not None,
        "expected_mpn_count": len(expected) if expected is not None else None,
        "missing_mpn_count": len(expected - discovered_logic) if expected is not None else None,
        "missing_executable_mpn_count": len(expected - executable_logic) if expected is not None else None,
        "missing_qualified_mpn_count": len(expected - qualified_logic) if expected is not None else None,
        "unexpected_mpn_count": len(discovered_logic - expected) if expected is not None else None,
        "status": (
            "complete" if expected is not None and not (expected - executable_logic)
            else "incomplete" if expected is not None else "unknown_universe"
        ),
        "qualification_status": (
            "complete" if expected is not None and not (expected - qualified_logic)
            else "incomplete" if expected is not None else "unknown_universe"
        ),
        "limitation": manifest_problem,
    }
    if manifest_problem and logic_manifest is not None:
        issues.append("54/74 manifest excluded: " + manifest_problem)

    distinct = set().union(*(value["discovered"] for value in by_category.values()), discovered_logic)
    return {
        "contract": CONTRACT,
        "distinct_mpn_count": len(distinct),
        "categories": categories,
        "logic_54_74": logic_report,
        "issues": issues,
        "gates": [
            "Acquire exact applicable models with redistribution/license review and immutable hashes.",
            "Record electrical model pins and map them to the exact orderable package.",
            "Pass parser and solver execution tests with digest-bound artifacts for every counted MPN.",
            "Qualify operating point, AC/transient behavior, limits, temperature and failure envelopes against suitable references.",
            "Use a sourced authoritative 54/74 universe manifest; do not replace exhaustive coverage with an invented count.",
        ],
    }


def format_coverage_report(report=None):
    """Return compact plain text suitable for a UI details pane or log."""
    report = deepcopy(report) if report is not None else audit_active_library()
    lines = ["Active model coverage (distinct manufacturer + MPN)"]
    for name in ACTIVE_CATEGORIES:
        item = report["categories"][name]
        lines.append(
            f"{name}: discovery {item['discovered']}; executable {item['executable']}/{item['target']}; "
            f"qualified {item['qualified']}; gap {item['gap']}"
        )
    logic = report["logic_54_74"]
    lines.append(
        f"54/74: discovery {logic['discovered']}; executable {logic['executable']}; "
        f"qualified {logic['qualified']}; exhaustive status {logic['status']} (no invented numeric target)"
    )
    if report["issues"]:
        lines.append(f"Excluded/duplicate claims: {len(report['issues'])}")
    return "\n".join(lines)
