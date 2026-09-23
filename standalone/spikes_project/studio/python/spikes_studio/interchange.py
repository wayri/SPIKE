"""Explicit format detection and loss-reporting interchange boundaries."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from .document import Document
from .model_import import convert_model_statement


@dataclass
class ImportReport:
    format: str
    source: str
    document: Document | None
    inventory: list
    warnings: list[str]


def sexpr(text):
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', text)
    stack, roots = [], []
    for token in tokens:
        if token == "(":
            child = []
            (stack[-1] if stack else roots).append(child)
            stack.append(child)
            if len(stack) > 128: raise ValueError("S-expression nesting exceeds 128")
        elif token == ")":
            if not stack: raise ValueError("Unmatched closing parenthesis")
            stack.pop()
        else:
            if not stack: raise ValueError("Atom outside S-expression")
            stack[-1].append(json.loads(token) if token.startswith('"') else token)
    if stack or len(roots) != 1: raise ValueError("Incomplete S-expression")
    return roots[0]


def detect(text):
    text = text.lstrip("\ufeff \r\n\t")
    if text.startswith("{"): return "spikes"
    if text.startswith("(kicad_sch"): return "kicad"
    if re.match(r"Version\s+4\b", text): return "ltspice_asc"
    if text.startswith("«") or text.startswith("\ufffd"): return "qspice_qsch"
    if re.match(r"(?im)^\s*\.model\s", text): return "model" if not re.search(r"(?im)^\s*[RCLVIX]\w+\s", text) else "spice_netlist"
    return "spice_netlist"


def import_text(text):
    if len(text.encode("utf-8")) > 16 * 1024 * 1024: raise ValueError("Import exceeds 16 MiB")
    fmt = detect(text)
    if fmt == "spikes": return ImportReport(fmt, text, Document(json.loads(text)), [], [])
    if fmt == "model": return ImportReport(fmt, text, None, [convert_model_statement(text)], ["Model draft created; choose pins/backend before placement."])
    if fmt == "kicad":
        tree = sexpr(text)
        inventory = []
        for child in tree:
            if isinstance(child, list) and child and child[0] == "symbol":
                props = {p[1]: p[2] for p in child if isinstance(p, list) and len(p) >= 3 and p[0] == "property"}
                inventory.append(props)
        return ImportReport(fmt, text, None, inventory, ["KiCad inventory and original source preserved. Electrical pin/net translation is not implemented; export a SPICE netlist in KiCad to simulate."])
    if fmt == "ltspice_asc":
        inventory = []
        for line in text.splitlines():
            if line.startswith("SYMBOL "): inventory.append({"symbol": line[7:], "attributes": {}})
            elif line.startswith("SYMATTR ") and inventory:
                fields = line.split(" ", 2)
                if len(fields) == 3: inventory[-1]["attributes"][fields[1]] = fields[2]
        return ImportReport(fmt, text, None, inventory, ["LTspice drawing inventory preserved. Use its SPICE netlist for simulation; .asy pin resolution and drawing translation are not implemented."])
    if fmt == "qspice_qsch":
        return ImportReport(fmt, text, None, [], ["QSPICE drawing source preserved. Export its SPICE netlist for executable interchange; .qsch geometry translation is not implemented."])
    return ImportReport(fmt, text, Document.from_netlist(text), [], [])


def export_netlist(document):
    from python.spikes.netlist import parse_netlist
    parse_netlist(document.data["source"])
    return document.data["source"]
