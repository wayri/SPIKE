# SPDX-License-Identifier: Apache-2.0
"""Pure controller-board block records and generic-controller conversion.

Board records are copied into blocks so saved projects do not silently change
when the built-in catalog is updated.  This module never imports or executes
firmware; it only prepares the existing sampled C controller contract.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import math
import re
import uuid

from .controller_block import CONTRACT as CONTROLLER_CONTRACT


MODES = frozenset(("NC", "AI", "DI", "AO", "DO"))
IO_ROLES = frozenset(("gpio", "analog"))
IO_CAPABILITIES = frozenset(("gpio", "digital_io", "digital_input", "digital_output", "analog_input", "analog_output"))
MODE_CAPABILITIES = {
    "AI": frozenset(("analog_input",)),
    "AO": frozenset(("analog_output",)),
    "DI": frozenset(("gpio", "digital_io", "digital_input")),
    "DO": frozenset(("gpio", "digital_io", "digital_output")),
}
COORDINATE_LIMIT = 1_000_000.0
MAX_BLOCKS = 256


def _identifier(value):
    text = re.sub(r"[^A-Za-z0-9_]", "_", str(value)).strip("_")
    text = re.sub(r"_+", "_", text) or "pin"
    if not text[0].isalpha():
        text = "pin_" + text
    if len(text) > 32:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
        text = text[:23].rstrip("_") + "_" + digest
    return text


def _code_names(pins):
    """Return deterministic, controller-safe names for all physical pins."""
    used = set()
    result = {}
    for pin in pins:
        base = _identifier(f"{pin['id']}_{pin.get('label', '')}")
        name = base
        suffix = 2
        while name.lower() in used:
            tail = f"_{suffix}"
            name = base[: 32 - len(tail)] + tail
            suffix += 1
        used.add(name.lower())
        result[pin["id"]] = name
    return result


def _finite_coordinate(value):
    return type(value) in (int, float) and math.isfinite(value) and abs(value) <= COORDINATE_LIMIT


def _bounded_text(value, field, *, maximum=256, allow_empty=False):
    if not isinstance(value, str) or len(value) > maximum or (not allow_empty and not value.strip()):
        raise ValueError(f"Controller-board {field} must be a bounded string")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(f"Controller-board {field} cannot contain control characters")


def _validate_board(board):
    if not isinstance(board, dict):
        raise ValueError("Controller board snapshot must be an object")
    for field in ("id", "name", "manufacturer", "family", "revision", "mcu", "connector_scope", "emulation_scope"):
        _bounded_text(board.get(field), field)
    if board.get("execution_status") != "pinout_template_only":
        raise ValueError("Controller-board execution status must be pinout_template_only")
    source_urls = board.get("source_urls")
    if not isinstance(source_urls, list) or len(source_urls) > 32:
        raise ValueError("Controller-board source URLs must be a bounded string list")
    for source_url in source_urls:
        _bounded_text(source_url, "source URL", maximum=2048)
    pins = board.get("pins")
    if not isinstance(pins, list) or not pins or len(pins) > 512:
        raise ValueError("Controller board needs 1..512 visible pins")
    seen = set()
    for pin in pins:
        if not isinstance(pin, dict):
            raise ValueError("Every controller-board pin needs an id")
        for field in ("id", "label", "header", "role"):
            _bounded_text(pin.get(field), f"pin {field}")
        if pin["id"] in seen:
            raise ValueError("Controller-board pin ids must be unique")
        seen.add(pin["id"])
        if type(pin.get("position")) is not int or not 1 <= pin["position"] <= 10000:
            raise ValueError("Controller-board pin positions must be positive bounded integers")
        aliases = pin.get("aliases", [])
        if not isinstance(aliases, list) or len(aliases) > 64:
            raise ValueError("Controller-board pin aliases must be a bounded string list")
        for alias in aliases:
            _bounded_text(alias, "pin alias")
        capabilities = pin.get("capabilities", [])
        if not isinstance(capabilities, list) or len(capabilities) > 64:
            raise ValueError("Controller-board pin capabilities must be a string list")
        for capability in capabilities:
            _bounded_text(capability, "pin capability")
    voltage = board.get("logic_voltage_v")
    if voltage is not None and (type(voltage) not in (int, float) or not math.isfinite(voltage) or not 0 < voltage <= 1000):
        raise ValueError("Controller-board logic voltage must be finite and positive")
    return pins


def _bindable(pin):
    return pin.get("role") in IO_ROLES and bool(IO_CAPABILITIES.intersection(pin.get("capabilities", ())))


def allowed_modes(pin):
    """Presentation and admission share the same declared pin capabilities."""
    return ('NC',) + tuple(mode for mode in ('AI','DI','AO','DO')
                           if _bindable(pin) and MODE_CAPABILITIES[mode].intersection(pin.get('capabilities',())))


def create(record, x, y, ref=None, scope=""):
    """Create an unbound block containing an independent board snapshot."""
    board = deepcopy(record)
    pins = _validate_board(board)
    if not _finite_coordinate(x) or not _finite_coordinate(y):
        raise ValueError("Controller-board coordinates must be finite and bounded")
    if ref is None:
        ref = "MCU1"
    if not isinstance(ref, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]{0,63}", ref):
        raise ValueError("Controller-board reference must be a safe identifier")
    if not isinstance(scope, str) or (scope and (scope != scope.upper() or not re.fullmatch(r"[A-Z][A-Z0-9_.-]*(?::[A-Z][A-Z0-9_.-]*)*", scope))):
        raise ValueError("Controller-board scope must be an uppercase instance path or empty")
    names = _code_names(pins)
    vdd = board.get("logic_voltage_v") or 3.3
    bindings = {
        pin["id"]: {
            "mode": "NC", "node": "", "reference": "", "source": "",
            "vdd": float(vdd), "code_name": names[pin["id"]],
        }
        for pin in pins
    }
    return {
        "id": "controller-board-" + uuid.uuid4().hex,
        "ref": ref,
        "board": board,
        "x": float(x),
        "y": float(y),
        "scope": scope,
        "bindings": bindings,
    }


def validate(blocks):
    """Validate a complete saved block list and return it unchanged."""
    if not isinstance(blocks, list) or len(blocks) > MAX_BLOCKS:
        raise ValueError(f"Controller-board blocks must be a list of at most {MAX_BLOCKS}")
    ids, refs = set(), set()
    for block in blocks:
        if not isinstance(block, dict):
            raise ValueError("Controller-board block must be an object")
        ident, ref = block.get("id"), block.get("ref")
        if not isinstance(ident, str) or not ident or ident in ids:
            raise ValueError("Controller-board block ids must be non-empty and unique")
        if not isinstance(ref, str) or not ref or ref.lower() in refs:
            raise ValueError("Controller-board references must be non-empty and unique")
        ids.add(ident); refs.add(ref.lower())
        scope = block.get("scope")
        if not isinstance(scope, str) or (scope and (scope != scope.upper() or not re.fullmatch(r"[A-Z][A-Z0-9_.-]*(?::[A-Z][A-Z0-9_.-]*)*", scope))):
            raise ValueError("Controller-board scope must be an uppercase instance path or empty")
        if not _finite_coordinate(block.get("x")) or not _finite_coordinate(block.get("y")):
            raise ValueError("Controller-board coordinates must be finite and bounded")
        pins = _validate_board(block.get("board"))
        if block.get('firmware_coupling_mode','legacy') not in ('legacy','electrical','timestamped','synchronous','peripheral'):
            raise ValueError('Unknown firmware coupling mode')
        if 'electrical_pads' in block:
            from .firmware_pad_settings import validate as validate_pads
            validate_pads(block['electrical_pads'],block['board'])
        pin_by_id = {pin["id"]: pin for pin in pins}
        bindings = block.get("bindings")
        if not isinstance(bindings, dict) or set(bindings) != set(pin_by_id):
            raise ValueError("Bindings must cover every visible board pin exactly once")
        code_names, output_sources = set(), set()
        for pin_id, binding in bindings.items():
            if not isinstance(binding, dict) or set(binding) != {"mode", "node", "reference", "source", "vdd", "code_name"}:
                raise ValueError("Invalid controller-board pin binding")
            mode = binding["mode"]
            if mode not in MODES:
                raise ValueError("Controller-board pin mode must be NC, AI, DI, AO, or DO")
            if mode != "NC" and not _bindable(pin_by_id[pin_id]):
                raise ValueError("Power, ground, reset, debug, and other non-I/O pins cannot be bound")
            if mode != "NC" and not MODE_CAPABILITIES[mode].intersection(pin_by_id[pin_id].get("capabilities", ())):
                raise ValueError("Controller-board binding mode is not declared by the pin capabilities")
            name = binding["code_name"]
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,31}", name) or name.lower() in code_names:
                raise ValueError("Controller-board code names must be unique safe identifiers")
            code_names.add(name.lower())
            vdd = binding["vdd"]
            if type(vdd) not in (int, float) or not math.isfinite(vdd) or not 0 < vdd <= 1000:
                raise ValueError("Controller-board pin VDD must be in (0,1000] V")
            for field in ("node", "reference", "source"):
                if not isinstance(binding[field], str):
                    raise ValueError("Controller-board connection fields must be strings")
            if mode == "NC" and any(binding[field] for field in ("node", "reference", "source")):
                raise ValueError("NC controller-board pins cannot retain circuit bindings")
            if mode.endswith("I") and (not binding["node"] or not binding["reference"] or binding["source"]):
                raise ValueError("Controller-board inputs need node/reference only")
            if mode.endswith("O"):
                source = binding["source"]
                if binding["node"] or binding["reference"] or not source or source in output_sources:
                    raise ValueError("Controller-board outputs need one unique source only")
                output_sources.add(source)
    return blocks


def _validate_project(config, project):
    from python.spikes.native_runner import _nodes
    nodes = set(_nodes(project))
    sources = {
        element.name
        for element in project.elements
        if element.kind == "voltage_source" and element.waveform is None
    }
    for pin in config["pins"]:
        if pin["mode"].endswith("I"):
            if pin["node"] not in nodes or pin["reference"] not in nodes:
                raise ValueError("Controller-board input references a missing exact project node")
        elif pin["source"] not in sources:
            raise ValueError("Controller-board output must bind an exact independent DC voltage source")


def _mapped_pins(block):
    pins = []
    for pin in block["board"]["pins"]:
        binding = block["bindings"][pin["id"]]
        if binding["mode"] == "NC":
            continue
        item = {"name": binding["code_name"], "mode": binding["mode"], "vdd": binding["vdd"]}
        if binding["mode"].endswith("I"):
            item.update(node=binding["node"], reference=binding["reference"], source="")
        else:
            item.update(node="", reference="", source=binding["source"])
        pins.append(item)
    return pins


def validate_attachment(config, blocks):
    """Validate an optional saved board-to-controller identity link.

    Legacy and generic controller configurations without ``board_block_id``
    remain independent.  This check compares data only and never compiles or
    executes the saved source.
    """
    if config is None or "board_block_id" not in config:
        return
    block_id = config.get("board_block_id")
    if not isinstance(block_id, str) or not block_id:
        raise ValueError("Attached controller needs a board_block_id")
    matches = [block for block in blocks if block.get("id") == block_id]
    if len(matches) != 1:
        raise ValueError("Attached controller board block does not exist")
    if config.get("pins") != _mapped_pins(matches[0]):
        raise ValueError("Attached controller pins no longer match the board bindings")


def controller_config(block, project=None, step_s=1e-4):
    """Convert one board block to the existing sampled generic-controller config.

    The generated C is an inert safe starting point.  ``IN_<name>`` and
    ``OUT_<name>`` index macros are supplied by :mod:`controller_block` when a
    user later explicitly trusts and compiles edited controller code.
    """
    validate([block])
    if type(step_s) not in (int, float) or not math.isfinite(step_s) or not 1e-12 <= step_s <= 1:
        raise ValueError("Controller step must be 1 ps..1 s")
    pins = _mapped_pins(block)
    if not 2 <= len(pins) <= 64 or not any(pin["mode"].endswith("I") for pin in pins) or not any(pin["mode"].endswith("O") for pin in pins):
        raise ValueError("Map 1..63 inputs and 1..63 outputs, with at most 64 mapped pins total")
    output_count = sum(pin["mode"].endswith("O") for pin in pins)
    source = "/* Pin indexes are provided as IN_<code_name> and OUT_<code_name> macros.\n"
    for pin in pins:
        prefix = "IN_" if pin["mode"].endswith("I") else "OUT_"
        source += f" * {prefix}{pin['name']} maps the explicitly bound {pin['mode']} pin.\n"
    source += " * This pinout template does not emulate the board or MCU. */\n"
    source += "void control_step(double time_s, double step_s, const double *inputs,\n"
    source += "                  double *outputs, double *state) {\n"
    source += "    (void)time_s; (void)step_s; (void)inputs; (void)state;\n"
    source += f"    for (int i = 0; i < {output_count}; ++i) outputs[i] = 0.0;\n"
    source += "}\n"
    config = {
        "contract": CONTROLLER_CONTRACT,
        "language": "C",
        "step_s": float(step_s),
        "state_count": 1,
        "pins": pins,
        "source": source,
        "board_block_id": block["id"],
        "board": deepcopy(block["board"]),
    }
    if project is not None:
        _validate_project(config, project)
    from .controller_block import validate as validate_controller
    validate_controller(config)
    return config


def add(document, block):
    """Append a block through one atomic :class:`Document` transaction."""
    candidate = deepcopy(block)
    def mutate(data):
        blocks = data.setdefault("controller_boards", [])
        validate(blocks + [candidate])
        blocks.append(candidate)
    document.commit(mutate)
    return candidate["id"]


def update(document, block_id, replacement):
    candidate = deepcopy(replacement)
    if candidate.get("id") != block_id:
        raise ValueError("A controller-board block id cannot be changed")
    def mutate(data):
        blocks = data.setdefault("controller_boards", [])
        indexes = [index for index, block in enumerate(blocks) if block.get("id") == block_id]
        if len(indexes) != 1:
            raise ValueError("Controller-board block no longer exists")
        old = blocks[indexes[0]]
        changed = list(blocks); changed[indexes[0]] = candidate
        validate(changed); blocks[indexes[0]] = candidate
        setup = data.get("controller_setup")
        if (setup or {}).get("board_block_id") == block_id and (old.get("board") != candidate.get("board") or old.get("bindings") != candidate.get("bindings")):
            drafts = data.setdefault("metadata", {}).setdefault("controller_board_detached_drafts", {})
            if not isinstance(drafts, dict):
                raise ValueError("Detached controller-board drafts must be an object")
            if block_id not in drafts and len(drafts) >= MAX_BLOCKS:
                raise ValueError("At most 256 detached controller-board drafts are retained; export or explicitly remove a retained draft before editing this attached board")
            drafts[block_id] = deepcopy(setup)
            data["controller_setup"] = None
    document.commit(mutate)


def remove(document, block_id):
    def mutate(data):
        blocks = data.setdefault("controller_boards", [])
        if (data.get("controller_setup") or {}).get("board_block_id") == block_id:
            raise ValueError("Detach the saved controller setup before removing its board block")
        changed = [block for block in blocks if block.get("id") != block_id]
        if len(changed) != len(blocks) - 1:
            raise ValueError("Controller-board block no longer exists")
        validate(changed); data["controller_boards"] = changed
    document.commit(mutate)
