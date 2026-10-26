# SPDX-License-Identifier: Apache-2.0
"""Compile explicit retained electrical bonds into passive native R/L branches."""
import copy
import json
import math


def compile_electrical_bonds(models, assembly, elements, reference, error):
    """Retained endpoints bind occurrence identity; local node maps are explicit.

    No resistance is inferred from contact area, placement, or material. The
    supplied R/L values override retained descriptive bond metadata. Native MNA
    owns all constitutive equations, singularity checks, and numerical solving.
    """
    expected = {bond.id: bond for bond in assembly.electrical_bonds}
    if not isinstance(models, list) or len(models) != len(expected):
        raise error("electrical_bond_models must cover every retained electrical bond exactly once.")
    owners = {item.id for item in [*assembly.boards, *assembly.parts]}

    def retained_owner(endpoint):
        if endpoint in owners:
            return endpoint
        matches = [owner for owner in owners if endpoint.startswith(owner + "::") or endpoint.startswith(owner + ":")]
        if len(matches) != 1:
            raise error("Retained electrical bond endpoint needs an unambiguous occurrence owner.")
        return matches[0]

    seen, result = set(), []
    for model in models:
        fields = {"bond_id", "endpoint_a", "endpoint_b", "resistance_ohm", "inductance_h"}
        if not isinstance(model, dict) or set(model) != fields:
            raise error("Electrical bond model requires bond_id, endpoint_a/b, resistance_ohm and inductance_h.")
        key = model["bond_id"]
        if not isinstance(key, str) or key not in expected or key in seen:
            raise error("Unknown or duplicate electrical bond model identity.")
        seen.add(key)
        terminals = []
        for field in ("endpoint_a", "endpoint_b"):
            ref = model[field]
            terminal = reference(ref)
            if ref.get("board_id", ref.get("part_id")) != retained_owner(getattr(expected[key], field)):
                raise error("Electrical bond endpoint owner differs from the retained bond.")
            terminals.append(terminal)
        if terminals[0] == terminals[1]:
            raise error("Electrical bond endpoints must reference distinct circuit nodes.")
        values = []
        for field in ("resistance_ohm", "inductance_h"):
            value = model[field]
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise error("Electrical bond R/L must be finite nonnegative numbers.")
            values.append(float(value))
        r, l = values
        prefix = "bond" + json.dumps([key], separators=(",", ":"), ensure_ascii=True)
        p, n = terminals
        ids = []
        for kind, field, value in (("resistor", "resistance_ohm", r), ("inductor", "inductance_h", l)):
            if not value:
                continue
            target = prefix + ":internal" if kind == "resistor" and l else n
            identifier = prefix + ":" + kind
            elements.append({"id": identifier, "type": kind, "positive_node": p, "negative_node": target, field: value})
            ids.append(identifier)
            p = target
        if not r and not l:
            identifier = prefix + ":ideal"
            elements.append({"id": identifier, "type": "voltage_source", "positive_node": p, "negative_node": n,
                             "dc_value": 0, "ac_magnitude": 0})
            ids.append(identifier)
        result.append({"bond_id": key, "element_ids": ids, "series_current_element_id": ids[0],
                       "properties": copy.deepcopy(model), "total_series_resistance_ohm": r, "total_series_inductance_h": l})
    return result
