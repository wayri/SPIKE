# SPDX-License-Identifier: Apache-2.0
"""Bounded KiCad schematic import, rendering and cross-selection admission.

KiCad owns rendering and netlist compilation.  This adapter retains only inert
SVG, source identity/geometry, and compiled connectivity; parser objects never
cross the service boundary.
"""

from __future__ import annotations

import hashlib
import math
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable

from python.core.board_parser import KicadParser

SCHEMATIC_VIEW_CONTRACT = "spike/kicad-schematic-view/v1"
MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_OUTPUT_BYTES = 64 * 1024 * 1024
MAX_HIERARCHY_SOURCE_BYTES = 32 * 1024 * 1024
MAX_SVG_BYTES = 80 * 1024 * 1024
MAX_PAGES = 128
MAX_SYMBOLS = 100_000
MAX_NET_NODES = 500_000
DEFAULT_TIMEOUT_SECONDS = 90
_FORBIDDEN_XML = re.compile(r"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)
_ENTITY = re.compile(r"<!\s*ENTITY\b", re.IGNORECASE)
_DOCTYPE = re.compile(r"<!\s*DOCTYPE\b[^>]*>", re.IGNORECASE | re.DOTALL)
_FORBIDDEN_STYLE = re.compile(r"(?:url\s*\(|@import|expression\s*\()", re.IGNORECASE)
_UUID = re.compile(r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")
_ALLOWED_SVG_TAGS = {
    "svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon",
    "text", "tspan", "defs", "clipPath", "mask", "pattern", "marker", "linearGradient",
    "radialGradient", "stop", "title", "desc", "style",
}


class KicadSchematicViewError(ValueError):
    """An admitted schematic could not be rendered safely."""


def _nodes(source: str) -> dict[str, Any]:
    parser = KicadParser.__new__(KicadParser)
    parser.parse_sexp(parser.tokenize(source))  # syntax/depth validation from the native adapter
    root: dict[str, Any] = {"atoms": [], "children": []}
    stack = [root]
    token_re = re.compile(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()]+')
    for match in token_re.finditer(source):
        token = match.group(0)
        if token == "(":
            node: dict[str, Any] = {"atoms": [], "children": []}
            stack[-1]["children"].append(node)
            stack.append(node)
        elif token == ")":
            if len(stack) == 1:
                raise KicadSchematicViewError("Malformed KiCad schematic expression.")
            stack.pop()
        else:
            stack[-1]["atoms"].append(_unquote(token))
    if len(stack) != 1:
        raise KicadSchematicViewError("Truncated KiCad schematic expression.")
    return root


def _unquote(token: str) -> str:
    if not (len(token) >= 2 and token[0] == token[-1] == '"'):
        return token
    # KiCad quoted fields use the usual small escape vocabulary.  Avoid a
    # general-purpose codec whose escape behavior changes arbitrary Unicode.
    return re.sub(r"\\([\\\"])", r"\1", token[1:-1])


def _head(node: dict[str, Any]) -> str:
    atoms = node.get("atoms", [])
    return str(atoms[0]) if atoms else ""


def _child(node: dict[str, Any], name: str) -> dict[str, Any] | None:
    return next((item for item in node.get("children", []) if _head(item) == name), None)


def _properties(node: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in node.get("children", []):
        atoms = item.get("atoms", [])
        if _head(item) == "property" and len(atoms) >= 3:
            result[str(atoms[1])] = str(atoms[2])
    return result


def _xy(node: dict[str, Any] | None, start: int = 1) -> tuple[float, float] | None:
    atoms = node.get("atoms", []) if node else []
    try:
        values = (float(atoms[start]), float(atoms[start + 1]))
    except (IndexError, TypeError, ValueError):
        return None
    return values if all(abs(value) <= 1_000_000 for value in values) else None


def _source_metadata(source: str, relative_file: str, sheet_path: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tree = _nodes(source)
    document = next((node for node in tree["children"] if _head(node) == "kicad_sch"), None)
    if document is None:
        raise KicadSchematicViewError("The selected file is not a modern KiCad schematic.")
    symbols: list[dict[str, Any]] = []
    child_sheets: list[dict[str, Any]] = []
    for node in document.get("children", []):
        kind = _head(node)
        if kind == "symbol" and _child(node, "lib_id") is not None:
            props = _properties(node)
            at = _xy(_child(node, "at"))
            uuid_node = _child(node, "uuid")
            uuid = str(uuid_node["atoms"][1]) if uuid_node and len(uuid_node["atoms"]) > 1 else ""
            if not at or not _UUID.fullmatch(uuid):
                continue
            reference = props.get("Reference", "")
            source_uuid = uuid.lower()
            occurrence_id = source_uuid if sheet_path == "/" else f"{source_uuid}@{sheet_path}"
            pins = []
            for pin in (item for item in node.get("children", []) if _head(item) == "pin"):
                pin_atoms = pin.get("atoms", [])
                pin_uuid = _child(pin, "uuid")
                if len(pin_atoms) > 1:
                    pins.append({
                        "number": str(pin_atoms[1]),
                        "uuid": str(pin_uuid["atoms"][1]).lower()
                        if pin_uuid and len(pin_uuid["atoms"]) > 1 and _UUID.fullmatch(str(pin_uuid["atoms"][1])) else "",
                    })
            symbols.append({
                "id": occurrence_id, "source_uuid": source_uuid, "reference": reference,
                "value": props.get("Value", ""), "lib_id": str(_child(node, "lib_id")["atoms"][1]),
                "sheet_path": sheet_path, "source_file": relative_file,
                "position_mm": {"x": at[0], "y": at[1]},
                "pins": pins,
                # Source symbols have no explicit outline envelope. This stable
                # pick envelope is deliberately labelled approximate.
                "hit_box_mm": {"x": at[0] - 5.0, "y": at[1] - 5.0, "width": 10.0, "height": 10.0,
                               "quality": "approximate_source_anchor"},
            })
        elif kind == "sheet":
            props = _properties(node)
            file_name = props.get("Sheet file", "")
            if file_name:
                uuid_node = _child(node, "uuid")
                child_sheets.append({
                    "name": props.get("Sheet name", Path(file_name).stem), "file": file_name,
                    "uuid": str(uuid_node["atoms"][1]).lower() if uuid_node and len(uuid_node["atoms"]) > 1 else "",
                })
    if len(symbols) > MAX_SYMBOLS:
        raise KicadSchematicViewError("The schematic exceeds the symbol admission limit.")
    return symbols, child_sheets


def _sheet_page_numbers(source: str) -> dict[str, int]:
    tree = _nodes(source)
    document = next((node for node in tree["children"] if _head(node) == "kicad_sch"), None)
    instances = _child(document, "sheet_instances") if document else None
    result: dict[str, int] = {}
    for path_node in instances.get("children", []) if instances else []:
        atoms = path_node.get("atoms", [])
        page_node = _child(path_node, "page")
        if _head(path_node) != "path" or len(atoms) < 2 or not page_node or len(page_node["atoms"]) < 2:
            continue
        try:
            page = int(page_node["atoms"][1])
        except (TypeError, ValueError):
            continue
        path = str(atoms[1])
        result[path if path == "/" else f"/{path.strip('/')}/"] = page
    return result


def _read_hierarchy(root_file: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    root_dir = root_file.parent.resolve()
    pending = [(root_file.resolve(), "/", frozenset())]
    visited: set[tuple[Path, str]] = set()
    pages: list[dict[str, Any]] = []
    symbols: list[dict[str, Any]] = []
    source_files: list[dict[str, Any]] = []
    total_source_bytes = 0
    page_numbers: dict[str, int] = {}
    while pending:
        path, sheet_path, ancestors = pending.pop(0)
        occurrence = (path, sheet_path)
        if occurrence in visited:
            continue
        try:
            path.relative_to(root_dir)
        except ValueError as exc:
            raise KicadSchematicViewError("Hierarchical sheet files must stay in the selected schematic directory.")
        if not path.is_file() or path.suffix.lower() != ".kicad_sch":
            raise KicadSchematicViewError(f"Missing hierarchical sheet: {path.name}")
        if path.stat().st_size > MAX_SOURCE_BYTES:
            raise KicadSchematicViewError(f"Schematic source exceeds {MAX_SOURCE_BYTES} bytes: {path.name}")
        source_bytes = path.read_bytes()
        total_source_bytes += len(source_bytes)
        if total_source_bytes > MAX_HIERARCHY_SOURCE_BYTES:
            raise KicadSchematicViewError("The schematic hierarchy exceeds the aggregate source-size limit.")
        source = source_bytes.decode("utf-8")
        if sheet_path == "/":
            page_numbers = _sheet_page_numbers(source)
        page_symbols, children = _source_metadata(source, path.name, sheet_path)
        symbols.extend(page_symbols)
        page_number = page_numbers.get(sheet_path, len(pages) + 1)
        pages.append({"page_id": f"page-{page_number}", "page_number": page_number,
                      "source_file": path.name, "sheet_path": sheet_path})
        for symbol in page_symbols:
            symbol["page_id"] = f"page-{page_number}"
        source_files.append({
            "file_name": str(path.relative_to(root_dir)).replace("\\", "/"),
            "sheet_path": sheet_path,
            "sha256": hashlib.sha256(source_bytes).hexdigest(),
            "content": source,
        })
        if len(pages) > MAX_PAGES or len(symbols) > MAX_SYMBOLS:
            raise KicadSchematicViewError("The schematic hierarchy exceeds the admission limits.")
        visited.add(occurrence)
        for child in children:
            declared = Path(str(child["file"]))
            if declared.is_absolute() or ".." in declared.parts:
                raise KicadSchematicViewError("Hierarchical sheet paths must be relative paths without traversal.")
            child_path = (root_dir / declared).resolve()
            try:
                child_path.relative_to(root_dir)
            except ValueError as exc:
                raise KicadSchematicViewError("Hierarchical sheet path escapes the selected schematic directory.")
            if child_path == path or child_path in ancestors:
                raise KicadSchematicViewError("The schematic hierarchy contains a file cycle.")
            component = child["uuid"] or hashlib.sha256(str(declared).encode()).hexdigest()[:16]
            pending.append((child_path, f"{sheet_path.rstrip('/')}/{component}/", ancestors | {path}))
    return pages, symbols, source_files


def _sanitize_svg(source: bytes) -> str:
    if len(source) > MAX_OUTPUT_BYTES:
        raise KicadSchematicViewError("A generated SVG exceeds the output admission limit.")
    text = source.decode("utf-8")
    if _ENTITY.search(text):
        raise KicadSchematicViewError("Generated SVG contains a forbidden XML entity declaration.")
    # KiCad emits the standard SVG public DOCTYPE. Discard it before parsing so
    # the returned artifact has no external subset or resolver dependency.
    text = _DOCTYPE.sub("", text)
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise KicadSchematicViewError("KiCad generated malformed SVG.") from exc
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag not in _ALLOWED_SVG_TAGS:
            raise KicadSchematicViewError(f"Generated SVG contains unsupported element: {tag}")
        for key, value in element.attrib.items():
            local = key.rsplit("}", 1)[-1].lower()
            compact = value.strip().lower()
            if local.startswith("on") or local in {"href", "src"} and not compact.startswith("#"):
                raise KicadSchematicViewError("Generated SVG contains an external or active reference.")
            if local == "style" and _FORBIDDEN_STYLE.search(value):
                raise KicadSchematicViewError("Generated SVG contains an external style reference.")
        if tag == "style" and _FORBIDDEN_STYLE.search(element.text or ""):
            raise KicadSchematicViewError("Generated SVG contains an external stylesheet reference.")
    return ET.tostring(root, encoding="unicode")


def _svg_view_box(source: str) -> list[float]:
    try:
        values = [float(value) for value in str(ET.fromstring(source).get("viewBox", "")).replace(",", " ").split()]
    except (ET.ParseError, TypeError, ValueError):
        return []
    return values if len(values) == 4 and all(math.isfinite(value) for value in values) else []


def _parse_netlist(source: bytes) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    if len(source) > MAX_OUTPUT_BYTES:
        raise KicadSchematicViewError("The generated netlist exceeds the output admission limit.")
    text = source.decode("utf-8")
    if _FORBIDDEN_XML.search(text):
        raise KicadSchematicViewError("Generated netlist contains forbidden XML declarations.")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise KicadSchematicViewError("KiCad generated a malformed XML netlist.") from exc
    components: list[dict[str, Any]] = []
    for component in root.findall("./components/comp"):
        reference = component.get("ref", "")
        components.append({
            "reference": reference,
            "value": component.findtext("value", default=""),
            "footprint": component.findtext("footprint", default=""),
        })
    nets: list[dict[str, Any]] = []
    reference_nets: dict[str, list[str]] = {}
    node_count = 0
    for net in root.findall("./nets/net"):
        name = net.get("name", "")
        nodes = []
        for node in net.findall("node"):
            node_count += 1
            if node_count > MAX_NET_NODES:
                raise KicadSchematicViewError("The netlist exceeds the connectivity admission limit.")
            reference, pin = node.get("ref", ""), node.get("pin", "")
            nodes.append({"reference": reference, "pin": pin, "pin_function": node.get("pinfunction", "")})
            if reference and name:
                reference_nets.setdefault(reference, []).append(name)
        nets.append({"code": net.get("code", ""), "name": name, "nodes": nodes})
    return nets, {key: sorted(set(value)) for key, value in reference_nets.items()}


def _diagnostics(*processes: subprocess.CompletedProcess[bytes]) -> list[str]:
    lines: list[str] = []
    for process in processes:
        text = (process.stdout + b"\n" + process.stderr).decode("utf-8", errors="replace")
        lines.extend(line.strip() for line in text.splitlines() if line.strip())
    return list(dict.fromkeys(lines))[-40:]


def _run(arguments: Iterable[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        list(arguments), cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=timeout, shell=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False,
    )


def import_kicad_schematic_view(
    source_path: str | Path, *, executable: str = "", timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Render a modern KiCad hierarchy into inert SVG pages plus connectivity."""
    path = Path(source_path).expanduser()
    if "\x00" in str(path) or path.suffix.lower() != ".kicad_sch" or not path.is_file():
        raise KicadSchematicViewError("Choose a readable .kicad_sch file.")
    path = path.resolve()
    source_pages, symbols, source_files = _read_hierarchy(path)
    cli = executable or shutil.which("kicad-cli") or shutil.which("kicad-cli.exe")
    if not cli:
        candidates = [Path(rf"C:\Program Files\KiCad\{version}\bin\kicad-cli.exe") for version in ("10.0", "9.0", "8.0")]
        cli = str(next((item for item in candidates if item.is_file()), ""))
    if not cli:
        raise KicadSchematicViewError("KiCad CLI is not installed or discoverable; schematic viewing is unavailable.")
    timeout = max(5, min(int(timeout_seconds), 300))
    with tempfile.TemporaryDirectory(prefix="spike-kicad-sch-") as temporary:
        output = Path(temporary)
        svg_process = _run((cli, "sch", "export", "svg", "--output", str(output), str(path)), output, timeout)
        netlist_path = output / "schematic.xml"
        net_process = _run((cli, "sch", "export", "netlist", "--format", "kicadxml", "--output", str(netlist_path), str(path)), output, timeout)
        diagnostics = _diagnostics(svg_process, net_process)
        svg_paths = sorted(output.glob("*.svg"), key=lambda item: item.name.casefold())
        if svg_process.returncode or net_process.returncode or not svg_paths or not netlist_path.is_file():
            detail = "\n".join(diagnostics[-8:])
            raise KicadSchematicViewError(f"KiCad schematic export failed.{(' ' + detail) if detail else ''}")
        if len(svg_paths) > MAX_PAGES:
            raise KicadSchematicViewError("KiCad generated too many schematic pages.")
        svg_pages = []
        svg_bytes = 0
        unassigned = list(svg_paths)
        render_order: list[tuple[dict[str, Any], Path]] = []
        for hierarchy_page in sorted(source_pages, key=lambda entry: entry["page_number"]):
            stem = Path(hierarchy_page["source_file"]).stem.casefold()
            item = next((candidate for candidate in unassigned if candidate.stem.casefold() == stem), None)
            if item is None:
                item = next((candidate for candidate in unassigned
                             if re.fullmatch(re.escape(stem) + r"(?:-|_)\d+", candidate.stem.casefold())), None)
            if item is None:
                item = unassigned[0] if unassigned else None
            if item is None:
                break
            unassigned.remove(item)
            render_order.append((hierarchy_page, item))
        for hierarchy_page, item in render_order:
            raw_svg = item.read_bytes()
            svg_bytes += len(raw_svg)
            if svg_bytes > MAX_SVG_BYTES:
                raise KicadSchematicViewError("Generated schematic SVG pages exceed the aggregate output limit.")
            sanitized = _sanitize_svg(raw_svg)
            page_number = int(hierarchy_page["page_number"])
            svg_pages.append({"id": f"page-{page_number}", "name": item.stem,
                              "sheet_path": hierarchy_page.get("sheet_path", ""),
                              "source_file": hierarchy_page.get("source_file", ""),
                              "view_box": _svg_view_box(sanitized), "svg": sanitized})
        nets, reference_nets = _parse_netlist(netlist_path.read_bytes())
    by_reference: dict[str, list[str]] = {}
    symbols_by_reference: dict[str, list[dict[str, Any]]] = {}
    for symbol in symbols:
        symbol["nets"] = reference_nets.get(symbol["reference"], [])
        by_reference.setdefault(symbol["reference"], []).append(symbol["id"])
        symbols_by_reference.setdefault(symbol["reference"], []).append(symbol)
    for net in nets:
        for node in net["nodes"]:
            matches = symbols_by_reference.get(node["reference"], [])
            node["symbol_ids"] = [item["id"] for item in matches]
            node["pin_uuids"] = [
                pin["uuid"] for item in matches for pin in item["pins"]
                if pin["number"] == node["pin"] and pin["uuid"]
            ]
    return {
        "contract": SCHEMATIC_VIEW_CONTRACT,
        "source": {"file_name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                   "format": "kicad_sch", "units": "mm"},
        "pages": svg_pages, "hierarchy": source_pages, "source_files": source_files,
        "symbols": symbols, "nets": nets,
        "cross_selection": {"reference_to_symbol_ids": by_reference},
        "diagnostics": diagnostics,
        "limitations": [
            "Symbol hit boxes are approximate source-anchor envelopes; KiCad does not export per-symbol SVG bounds.",
            "SVG page artwork and source symbol identities are correlated by sheet/reference metadata, not rewritten SVG elements.",
        ],
    }


def handle_kicad_schematic_request(method: Any, params: dict[str, Any]) -> dict[str, Any] | None:
    """Return a raw result for service composition, or ``None`` for other methods."""
    if method != "import_kicad_schematic_view":
        return None
    if not isinstance(params, dict):
        raise KicadSchematicViewError("Schematic import parameters must be an object.")
    return import_kicad_schematic_view(
        str(params.get("path", "")), timeout_seconds=int(params.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)),
    )
