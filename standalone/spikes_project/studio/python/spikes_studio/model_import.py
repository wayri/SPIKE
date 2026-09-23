"""Convert one pasted SPICE .MODEL statement into a schematic part contract.

The converter preserves expressions as text and assigns a conventional symbol
and pin set only when the SPICE model type is known.  It deliberately does not
claim that the current solver can execute every accepted model family.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


MODEL_IMPORT_CONTRACT = "spikes/model-statement-import/v1"
STUDIO_PART_CONTRACT = "spikes/studio-part/v1"
MAX_MODEL_BYTES = 1024 * 1024
MAX_PARAMETERS = 4096

_MODEL_RE = re.compile(
    r"^\s*\.model\s+([A-Za-z_][A-Za-z0-9_.$+-]{0,127})\s+"
    r"([A-Za-z][A-Za-z0-9_-]{0,63})\s*(.*?)\s*$",
    flags=re.IGNORECASE | re.DOTALL,
)
_PARAMETER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.$-]{0,127}$", re.ASCII)


class ModelImportError(ValueError):
    """A pasted statement is ambiguous, malformed, or exceeds a hard bound."""


@dataclass(frozen=True, slots=True)
class DeviceTemplate:
    family: str
    symbol: str
    prefix: str
    pins: tuple[str, ...]
    optional_pins: tuple[str, ...] = ()
    simulation_backend: str = "requires_compact_model_backend"


_TEMPLATES: dict[str, DeviceTemplate] = {
    "D": DeviceTemplate("diode", "semiconductor.diode", "D", ("a", "k"), simulation_backend="native_diode"),
    "NPN": DeviceTemplate("bjt_npn", "semiconductor.bjt_npn", "Q", ("c", "b", "e"), ("s",)),
    "PNP": DeviceTemplate("bjt_pnp", "semiconductor.bjt_pnp", "Q", ("c", "b", "e"), ("s",)),
    "NMOS": DeviceTemplate("mosfet_n", "semiconductor.mosfet_n", "M", ("d", "g", "s", "b")),
    "PMOS": DeviceTemplate("mosfet_p", "semiconductor.mosfet_p", "M", ("d", "g", "s", "b")),
    "MOS": DeviceTemplate("mosfet", "semiconductor.mosfet", "M", ("d", "g", "s", "b")),
    "NJF": DeviceTemplate("jfet_n", "semiconductor.jfet_n", "J", ("d", "g", "s")),
    "PJF": DeviceTemplate("jfet_p", "semiconductor.jfet_p", "J", ("d", "g", "s")),
    "NMES": DeviceTemplate("mesfet_n", "semiconductor.mesfet_n", "Z", ("d", "g", "s")),
    "PMES": DeviceTemplate("mesfet_p", "semiconductor.mesfet_p", "Z", ("d", "g", "s")),
    "IGBT": DeviceTemplate("igbt", "semiconductor.igbt", "Z", ("c", "g", "e"), ("t",)),
    "NIGBT": DeviceTemplate("igbt_n", "semiconductor.igbt_n", "Z", ("c", "g", "e"), ("t",)),
    "PIGBT": DeviceTemplate("igbt_p", "semiconductor.igbt_p", "Z", ("c", "g", "e"), ("t",)),
    "SCR": DeviceTemplate("thyristor", "semiconductor.thyristor", "X", ("a", "k", "g")),
    "THYRISTOR": DeviceTemplate("thyristor", "semiconductor.thyristor", "X", ("a", "k", "g")),
    "SW": DeviceTemplate("voltage_controlled_switch", "switch.voltage_controlled", "S", ("p", "n", "cp", "cn")),
    "CSW": DeviceTemplate("current_controlled_switch", "switch.current_controlled", "W", ("p", "n"), ("control_source",)),
    "LTRA": DeviceTemplate("lossy_transmission_line", "transmission.lossy_line", "O", ("p1", "n1", "p2", "n2")),
    "URC": DeviceTemplate("uniform_distributed_rc", "transmission.urc", "U", ("p1", "p2", "ref")),
}


def _logical_statement(text: str) -> str:
    if not isinstance(text, str):
        raise ModelImportError("MODEL input must be text")
    encoded = text.encode("utf-8")
    if not encoded or len(encoded) > MAX_MODEL_BYTES or "\x00" in text:
        raise ModelImportError("MODEL input is empty or exceeds the 1 MiB limit")
    logical: list[str] = []
    for physical in text.splitlines():
        stripped = physical.strip()
        if not stripped or stripped.startswith("*"):
            continue
        if stripped.startswith("+"):
            if not logical:
                raise ModelImportError("A continuation line requires a preceding MODEL line")
            logical[-1] += " " + stripped[1:].strip()
        else:
            logical.append(stripped)
    if len(logical) != 1:
        raise ModelImportError("Paste exactly one .MODEL statement")
    return logical[0]


def _unwrap_parameters(tail: str) -> str:
    value = tail.strip()
    if not value:
        return ""
    if value.startswith("("):
        depth = 0
        quote = ""
        for index, char in enumerate(value):
            if quote:
                if char == quote:
                    quote = ""
                continue
            if char in {'\"', "'"}:
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth < 0:
                    raise ModelImportError("MODEL parameter parentheses are unbalanced")
                if depth == 0 and value[index + 1 :].strip():
                    raise ModelImportError("Unexpected text follows the MODEL parameter list")
        if depth != 0 or quote:
            raise ModelImportError("MODEL parameter parentheses or quotes are unbalanced")
        return value[1:-1].strip()
    return value


def _split_fields(text: str) -> tuple[str, ...]:
    fields: list[str] = []
    start = 0
    stack: list[str] = []
    quote = ""
    pairs = {")": "(", "}": "{", "]": "["}
    for index, char in enumerate(text):
        if quote:
            if char == quote and (index == 0 or text[index - 1] != "\\"):
                quote = ""
            continue
        if char in {'\"', "'"}:
            quote = char
        elif char in "({[":
            stack.append(char)
        elif char in ")} ]".replace(" ", ""):
            if not stack or stack.pop() != pairs[char]:
                raise ModelImportError("MODEL parameter delimiters are unbalanced")
        elif (char.isspace() or char == ",") and not stack:
            field = text[start:index].strip()
            if field:
                fields.append(field)
            start = index + 1
    if quote or stack:
        raise ModelImportError("MODEL parameter delimiters are unbalanced")
    field = text[start:].strip()
    if field:
        fields.append(field)
    return tuple(fields)


def _parameters(text: str) -> tuple[dict[str, Any], ...]:
    if not text:
        return ()
    fields = _split_fields(text)
    if len(fields) > MAX_PARAMETERS:
        raise ModelImportError(f"MODEL exceeds {MAX_PARAMETERS} parameters")
    result: list[dict[str, Any]] = []
    names: set[str] = set()
    for field in fields:
        if "=" in field:
            name, raw = field.split("=", 1)
            name = name.strip().upper()
            raw = raw.strip()
            if not raw:
                raise ModelImportError(f"MODEL parameter {name or '<empty>'} has no value")
        else:
            name, raw = field.strip().upper(), "true"
        if _PARAMETER_RE.fullmatch(name) is None:
            raise ModelImportError(f"Invalid MODEL parameter name: {name!r}")
        if name in names:
            raise ModelImportError(f"Duplicate MODEL parameter: {name}")
        names.add(name)
        result.append({"name": name, "value_text": raw})
    return tuple(result)


def parse_model_statement(text: str) -> dict[str, Any]:
    statement = _logical_statement(text)
    match = _MODEL_RE.fullmatch(statement)
    if match is None:
        raise ModelImportError("Expected '.MODEL NAME TYPE [(] PARAM=VALUE ... [)]'")
    name = match.group(1)
    model_type = match.group(2).upper()
    parameter_text = _unwrap_parameters(match.group(3) or "")
    parameters = _parameters(parameter_text)
    normalized_parameters = " ".join(
        item["name"] if item["value_text"] == "true" else f"{item['name']}={item['value_text']}"
        for item in parameters
    )
    normalized = f".MODEL {name} {model_type}"
    if normalized_parameters:
        normalized += f" ({normalized_parameters})"
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return {
        "contract": MODEL_IMPORT_CONTRACT,
        "name": name,
        "model_type": model_type,
        "parameters": list(parameters),
        "normalized_statement": normalized,
        "sha256": digest,
    }


def _technology_hint(name: str, parameters: Iterable[dict[str, Any]]) -> str:
    haystack = " ".join([name, *(str(item["value_text"]) for item in parameters)]).upper()
    if "GAN" in haystack:
        return "gan"
    if "SIC" in haystack or "SILICON_CARBIDE" in haystack:
        return "sic"
    if "DIAMOND" in haystack:
        return "diamond"
    return "unspecified"


def convert_model_statement(text: str, *, namespace: str = "local") -> dict[str, Any]:
    parsed = parse_model_statement(text)
    if re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", namespace, re.ASCII) is None:
        raise ModelImportError("Library namespace must be a lowercase identifier")
    template = _TEMPLATES.get(parsed["model_type"])
    known = template is not None
    if template is None:
        template = DeviceTemplate(
            "generic_spice_model", "generic.model_block", "X", (),
            simulation_backend="requires_user_pin_mapping_and_backend",
        )
    slug = re.sub(r"[^a-z0-9_.-]+", "-", parsed["name"].lower()).strip("-.") or "model"
    technology = _technology_hint(parsed["name"], parsed["parameters"])
    return {
        "contract": STUDIO_PART_CONTRACT,
        "part_id": f"{namespace}.spice:{slug}@1",
        "display_name": parsed["name"],
        "category": "semiconductor" if template.family not in {
            "lossy_transmission_line", "uniform_distributed_rc",
        } else "transmission",
        "family": template.family,
        "technology": technology,
        "symbol": {
            "library_id": f"spikes.{template.symbol}",
            "auto_generated": True,
            "editable": True,
        },
        "instance_prefix": template.prefix,
        "pins": [
            {"id": pin, "name": pin.upper(), "electrical_type": "passive"}
            for pin in template.pins
        ],
        "optional_pins": list(template.optional_pins),
        "requires_pin_mapping": not known,
        "model": parsed,
        "simulation": {
            "status": "runnable" if template.simulation_backend == "native_diode" else "backend_required",
            "backend": template.simulation_backend,
        },
        "qualification": {
            "state": "unreviewed",
            "redistribution_approved": False,
            "notes": "Pasted text is local user input; validate licensing and device accuracy before sharing or signoff.",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--statement")
    source.add_argument("--file", type=Path)
    parser.add_argument("--namespace", default="local")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    try:
        text = arguments.statement if arguments.statement is not None else arguments.file.read_text(encoding="utf-8")
        result = convert_model_statement(text, namespace=arguments.namespace)
        encoded = json.dumps(result, indent=2, allow_nan=False) + "\n"
        if arguments.output is None:
            sys.stdout.write(encoded)
        else:
            arguments.output.parent.mkdir(parents=True, exist_ok=True)
            arguments.output.write_text(encoded, encoding="utf-8")
        return 0
    except (OSError, UnicodeError, ModelImportError) as exc:
        sys.stderr.write(json.dumps({
            "contract": "spikes/model-import-error/v1", "status": "error",
            "message": str(exc),
        }, allow_nan=False) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
