# SPDX-License-Identifier: Apache-2.0
"""Import explicit net connectivity into a truthful generated diagram."""

from __future__ import annotations

import hashlib
import html
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .importers import ImportPolicy
from .kicad_schematic_importer import (
    KicadSchematicViewError, SCHEMATIC_VIEW_CONTRACT, _child, _head, _nodes,
    _properties, _sanitize_svg, _svg_view_box,
)
from .odb_importer import import_odb_design

MAX_TEXT_BYTES = 32 * 1024 * 1024
MAX_COMPONENTS = 5_000
MAX_NODES = 100_000
_FORBIDDEN_XML = re.compile(r"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)


class ConnectivityViewError(ValueError):
    """The selected source cannot provide unambiguous explicit connectivity."""


def _identity(reference: str) -> str:
    return "component-" + hashlib.sha256(reference.encode("utf-8")).hexdigest()[:24]


def _validate_connectivity(components: list[dict[str, Any]], nets: list[dict[str, Any]]) -> None:
    references = {item["reference"] for item in components}
    if "" in references or len(references) != len(components):
        raise ConnectivityViewError("Connectivity source contains an empty or duplicate component reference.")
    assignments: dict[tuple[str, str], str] = {}
    count = 0
    for net in nets:
        if not net["name"]:
            raise ConnectivityViewError("Connectivity source contains an unnamed net.")
        for node in net["nodes"]:
            count += 1
            if count > MAX_NODES:
                raise ConnectivityViewError("Connectivity source exceeds the pin-to-net admission limit.")
            reference, pin = node["reference"], node["pin"]
            if reference not in references or not pin:
                raise ConnectivityViewError(f"Net {net['name']} has an unknown component or empty pin.")
            key = (reference, pin)
            prior = assignments.setdefault(key, net["name"])
            if prior != net["name"]:
                raise ConnectivityViewError(
                    f"Component pin {reference}.{pin} is assigned to conflicting nets {prior} and {net['name']}."
                )


def _xml_text(path: Path) -> str:
    if path.stat().st_size > MAX_TEXT_BYTES:
        raise ConnectivityViewError("Connectivity source exceeds the 32 MiB text limit.")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ConnectivityViewError("Connectivity source must be UTF-8 text.") from exc


def _parse_kicad_xml(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if _FORBIDDEN_XML.search(text):
        raise ConnectivityViewError("KiCad XML netlists may not contain DTD or entity declarations.")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ConnectivityViewError("Malformed KiCad XML netlist.") from exc
    if root.tag != "export":
        raise ConnectivityViewError("The XML document is not a KiCad export netlist.")
    components = [{
        "reference": item.get("ref", ""), "value": item.findtext("value", default=""),
        "footprint": item.findtext("footprint", default=""),
    } for item in root.findall("./components/comp")]
    nets = []
    for item in root.findall("./nets/net"):
        nets.append({
            "code": item.get("code", ""), "name": item.get("name", ""),
            "nodes": [{"reference": node.get("ref", ""), "pin": node.get("pin", ""),
                       "pin_function": node.get("pinfunction", "")}
                      for node in item.findall("node")],
        })
    return components, nets


def _atom_value(node: dict[str, Any] | None, default: str = "") -> str:
    atoms = node.get("atoms", []) if node else []
    return str(atoms[1]) if len(atoms) > 1 else default


def _parse_kicad_net(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tree = _nodes(text)
    export = next((item for item in tree["children"] if _head(item) == "export"), None)
    if export is None:
        raise ConnectivityViewError("The .net file is not a KiCad s-expression export.")
    component_group = _child(export, "components")
    net_group = _child(export, "nets")
    components = []
    for item in component_group.get("children", []) if component_group else []:
        if _head(item) != "comp":
            continue
        components.append({
            "reference": _atom_value(_child(item, "ref")),
            "value": _atom_value(_child(item, "value")),
            "footprint": _atom_value(_child(item, "footprint")),
        })
    nets = []
    for item in net_group.get("children", []) if net_group else []:
        if _head(item) != "net":
            continue
        nodes = []
        for node in item.get("children", []):
            if _head(node) == "node":
                nodes.append({"reference": _atom_value(_child(node, "ref")),
                              "pin": _atom_value(_child(node, "pin")), "pin_function": ""})
        nets.append({"code": _atom_value(_child(item, "code")),
                     "name": _atom_value(_child(item, "name")), "nodes": nodes})
    return components, nets


def _parse_odb(path: Path, step: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    policy = ImportPolicy(max_source_bytes=512 * 1024 * 1024, max_archive_members=50_000,
                          max_archive_depth=8, max_expanded_bytes=2 * 1024 * 1024 * 1024,
                          max_compression_ratio=100.0, timeout_seconds=120)
    design = import_odb_design(str(path), step=step, policy=policy)
    net_names = {int(item["id"]): str(item["name"]) for item in design.nets}
    components = []
    nodes_by_net: dict[int, list[dict[str, str]]] = {key: [] for key in net_names}
    for item in design.components:
        reference = str(item.get("reference", ""))
        components.append({"reference": reference, "value": str(item.get("value", "")),
                           "footprint": str(item.get("footprint", ""))})
        for pin in item.get("pins", []):
            # ODB++ toeprints use the zero-based NET record index while the
            # normalized ODB net IDs are one-based.
            net_id = int(pin.get("net_index", -1)) + 1
            if net_id in net_names:
                nodes_by_net[net_id].append({"reference": reference, "pin": str(pin.get("number", "")),
                                             "pin_function": ""})
    nets = [{"code": str(key), "name": name, "nodes": nodes_by_net.get(key, [])}
            for key, name in sorted(net_names.items())]
    return components, nets, str(design.metadata.get("source_sha256", ""))


def _generated_svg(components: list[dict[str, Any]], nets: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    pins_by_ref: dict[str, list[tuple[str, str]]] = {item["reference"]: [] for item in components}
    for net in nets:
        for node in net["nodes"]:
            pins_by_ref[node["reference"]].append((node["pin"], net["name"]))
    rows = []
    symbols = []
    column_count, column_stride, column_width, pin_gap = 3, 400, 220, 32
    prepared = []
    for component in sorted(components, key=lambda item: item["reference"].casefold()):
        pins = sorted(pins_by_ref[component["reference"]], key=lambda item: (item[0], item[1]))
        prepared.append((component, pins, max(70, 42 + len(pins) * pin_gap)))
    row_heights = [max(item[2] for item in prepared[index:index + column_count])
                   for index in range(0, len(prepared), column_count)]
    row_y = []
    cursor = 40
    for height in row_heights:
        row_y.append(cursor)
        cursor += height + 45
    width = 30 + column_count * column_stride
    for index, (component, pins, height) in enumerate(prepared):
        column, row = index % column_count, index // column_count
        x, y = 30 + column * column_stride, row_y[row]
        component_id = _identity(component["reference"])
        rows.append(f'<g id="{component_id}"><rect x="{x}" y="{y}" width="{column_width}" height="{height}" rx="6"/>')
        rows.append(f'<text class="ref" x="{x + 10}" y="{y + 20}">{html.escape(component["reference"])}</text>')
        rows.append(f'<text x="{x + 10}" y="{y + 37}">{html.escape(component["value"])}</text>')
        pin_records = []
        for pin_index, (pin, net) in enumerate(pins):
            py = y + 58 + pin_index * pin_gap
            rows.append(f'<line x1="{x + column_width}" y1="{py}" x2="{x + column_width + 18}" y2="{py}"/>')
            rows.append(f'<text x="{x + column_width - 8}" y="{py + 4}" text-anchor="end">{html.escape(pin)}</text>')
            visible_net = net if len(net) <= 22 else net[:19] + "..."
            rows.append(f'<text class="net" x="{x + column_width + 22}" y="{py + 4}">'
                        f'<title>{html.escape(net)}</title>{html.escape(visible_net)}</text>')
            pin_records.append({"number": pin, "uuid": "", "net": net})
        rows.append("</g>")
        symbols.append({
            "id": component_id, "source_uuid": "", "reference": component["reference"],
            "value": component["value"], "lib_id": component["footprint"], "page_id": "page-1",
            "sheet_path": "/", "source_file": "", "position": {"x": x, "y": y, "units": "diagram"},
            "hit_box": {"x": x, "y": y, "width": column_width, "height": height,
                        "units": "diagram", "quality": "generated_connectivity"},
            "pins": pin_records, "nets": sorted({net for _, net in pins}),
        })
    height = max(180, cursor)
    style = "rect{fill:#f6f5ed;stroke:#426354}line{stroke:#426354}text{font:12px monospace;fill:#263d35}.ref{font-weight:bold}.net{fill:#346d9a;font-size:10px}"
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}"><style>{style}</style>{"".join(rows)}</svg>'
    return _sanitize_svg(svg.encode("utf-8")), symbols


def import_connectivity_view(path_value: str | Path, *, format_hint: str = "", step: str = "") -> dict[str, Any]:
    path = Path(path_value).expanduser()
    if "\x00" in str(path) or not path.exists():
        raise ConnectivityViewError("Choose a readable connectivity source.")
    suffix = path.suffix.lower()
    hint = format_hint.strip().lower()
    source_text = ""
    if hint in {"kicad_xml", "xml"} or not hint and suffix == ".xml":
        source_format = "kicad_xml_netlist"
        source_text = _xml_text(path)
        components, nets = _parse_kicad_xml(source_text)
        source_digest = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    elif hint in {"kicad_net", "net"} or not hint and suffix == ".net":
        source_format = "kicad_legacy_netlist"
        source_text = _xml_text(path)
        components, nets = _parse_kicad_net(source_text)
        source_digest = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    elif hint in {"odb", "odb++"} or path.is_dir() or suffix in {".zip", ".tgz", ".gz", ".tar"}:
        source_format = "odb++"
        components, nets, source_digest = _parse_odb(path.resolve(), step)
    else:
        raise ConnectivityViewError(
            "Unsupported connectivity source. Use a KiCad XML/.net netlist or an ODB++ job; generic SPICE and behavioral netlists are not admitted."
        )
    if not components or len(components) > MAX_COMPONENTS:
        raise ConnectivityViewError("Connectivity source has no components or exceeds the component admission limit.")
    _validate_connectivity(components, nets)
    svg, symbols = _generated_svg(components, nets)
    symbols_by_ref = {item["reference"]: item for item in symbols}
    for net in nets:
        for node in net["nodes"]:
            symbol = symbols_by_ref[node["reference"]]
            node["symbol_ids"] = [symbol["id"]]
            node["pin_uuids"] = []
    return {
        "contract": SCHEMATIC_VIEW_CONTRACT,
        "source": {"file_name": path.name, "sha256": source_digest, "format": source_format,
                   "presentation": "generated_connectivity", "units": "diagram"},
        "pages": [{"id": "page-1", "name": "Generated connectivity", "sheet_path": "/",
                   "source_file": path.name, "view_box": _svg_view_box(svg), "svg": svg}],
        "hierarchy": [{"page_id": "page-1", "page_number": 1, "source_file": path.name, "sheet_path": "/"}],
        "source_files": ([{"file_name": path.name, "sheet_path": "/", "sha256": source_digest,
                           "content": source_text}] if source_text else []),
        "symbols": symbols, "nets": nets,
        "cross_selection": {"reference_to_symbol_ids": {item["reference"]: [item["id"]] for item in symbols}},
        "diagnostics": [
            "No original schematic artwork was present; SPIKE generated this connectivity diagram from explicit component-pin-net records."
        ],
        "limitations": [
            "The diagram is generated from explicit connectivity; it is not original schematic artwork or placement.",
            "ODB++ connectivity is board/package connectivity and does not reconstruct schematic hierarchy or symbol graphics.",
            "Generic SPICE and behavioral netlists are unsupported because they do not provide one unambiguous component-pin identity contract.",
        ],
    }


def handle_connectivity_view_request(method: Any, params: dict[str, Any]) -> dict[str, Any] | None:
    if method != "import_connectivity_view":
        return None
    if not isinstance(params, dict):
        raise ConnectivityViewError("Connectivity import parameters must be an object.")
    return import_connectivity_view(str(params.get("path", "")), format_hint=str(params.get("format_hint", "")),
                                    step=str(params.get("step", "")))
