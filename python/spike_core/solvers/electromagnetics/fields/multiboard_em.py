# SPDX-License-Identifier: Apache-2.0
"""Explicit reciprocal RL loop coupling for assembly magnetic screening.

RMS phasors obey V = (diag(R) + j omega L) I. Supplied mutual inductances
must form a positive semidefinite energy matrix; no geometric extraction,
radiation prediction, or automatic coupling inferred from board proximity.
"""
import json
import math
import numpy as np
from ....spider_v2 import AssemblyIRV1
from ....harness_authoring import validate_harness_connections
from ....multiboard_identity import assembly_physics_digest, canonical_json_digest

REQUEST_CONTRACT = "spike/multiboard-em-request/v1"
RESULT_CONTRACT = "spike/multiboard-em-result/v1"


def _number(value, label, lower=0, positive=False):
    if type(value) not in (float, int) or not math.isfinite(value) or value < lower or (positive and value <= lower):
        raise ValueError(f"{label} must be a finite {'positive' if positive else 'non-negative'} number.")
    return float(value)


def _fields(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) or set(value) - set(required) - set(optional):
        raise ValueError(f"Expected fields {sorted(required)} and optional {sorted(optional)}.")


def _id(value):
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("EM identities require nonempty trimmed strings.")
    return value


def run_multiboard_em(raw):
    _fields(raw, {"contract", "assembly", "loops", "mutual_inductances", "frequency_hz", "connector_models"})
    if raw["contract"] != REQUEST_CONTRACT:
        raise ValueError("Unsupported multi-board EM contract.")
    encoded = json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(encoded) > 8 * 1024**2:
        raise ValueError("EM request exceeds 8 MiB.")
    assembly = AssemblyIRV1.from_dict(raw["assembly"])
    validate_harness_connections(assembly)
    board_ids = {b.id for b in assembly.boards}
    excluded_parts = [part.id for part in assembly.parts if part.part_type == "subassembly" and not part.model_id]
    part_ids = {part.id for part in assembly.parts} - set(excluded_parts)
    if assembly.rigid_flex_links or assembly.electrical_bonds:
        raise ValueError("Rigid-flex links and electrical bonds require a coupled topology model, unsupported by independent EM loops.")
    retained_owners = {("board_id", key) for key in board_ids} | {("part_id", key) for key in part_ids}
    loops = raw["loops"]
    if not isinstance(loops, list) or not 2 <= len(loops) <= 128 or not board_ids or len(retained_owners) < 2:
        raise ValueError("EM needs 2..128 loops on at least two retained board/part owners, including a board.")
    identities, owners, voltages, resistance, inductance = {}, set(), [], [], []
    loop_owners = []
    for row in loops:
        _fields(row, {"loop_id", "resistance_ohm", "self_inductance_h", "voltage_real_v", "voltage_imag_v"}, {"board_id", "part_id"})
        key = row["loop_id"]
        fields = set(row) & {"board_id", "part_id"}
        if len(fields) != 1:
            raise ValueError("Each loop needs exactly one board_id or part_id owner.")
        field = next(iter(fields))
        value = row[field]
        if not isinstance(value, str) or (field, value) not in retained_owners:
            raise ValueError("Loop owner must name a retained board or part.")
        owner = (field, value)
        if not isinstance(key, str) or not key.strip() or key != key.strip() or key in identities:
            raise ValueError("Loops need unique trimmed IDs.")
        identities[key] = len(identities)
        owners.add(owner)
        loop_owners.append(owner)
        resistance.append(_number(row["resistance_ohm"], "resistance_ohm", positive=True))
        inductance.append(_number(row["self_inductance_h"], "self_inductance_h", positive=True))
        voltage = []
        for field in ("voltage_real_v", "voltage_imag_v"):
            value = row[field]
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError("Drive voltages must be finite RMS phasors.")
            voltage.append(float(value))
        voltages.append(complex(*voltage))
    if owners != retained_owners:
        raise ValueError("Each retained board and part must have an explicit loop model.")
    # Contact properties contribute only to the declared loop, never across
    # unrelated boards. Verify pin membership in retained connector mappings.
    inventory = {}
    for mapping in assembly.connector_mappings:
        if mapping.kind != "connector-mate" and isinstance(mapping.data.get("pins"), dict):
            data = mapping.data
            inventory[(data.get("board_id"), data.get("connector_id"))] = set(data.get("pins", {}))
    contacts = raw["connector_models"]
    if not isinstance(contacts, list) or len(contacts) > 4096:
        raise ValueError("connector_models must contain at most 4096 entries.")
    seen_contacts = set()
    for contact in contacts:
        _fields(contact, {"loop_id", "board_id", "connector_id", "pin", "resistance_ohm", "inductance_h"})
        loop = identities.get(_id(contact["loop_id"]))
        key = tuple(_id(contact[field]) for field in ("board_id", "connector_id", "pin"))
        if loop is None or loops[loop].get("board_id") != contact["board_id"] or key in seen_contacts or contact["pin"] not in inventory.get(key[:2], set()):
            raise ValueError("Contact must own a unique retained connector pin on its loop board.")
        seen_contacts.add(key)
        resistance[loop] += _number(contact["resistance_ohm"], "contact resistance_ohm")
        inductance[loop] += _number(contact["inductance_h"], "contact inductance_h")
    matrix = np.diag(inductance)
    mutuals = raw["mutual_inductances"]
    if not isinstance(mutuals, list) or len(mutuals) > len(loops) * (len(loops)-1)//2:
        raise ValueError("Invalid mutual-inductance inventory.")
    pairs = set()
    for row in mutuals:
        _fields(row, {"loop_a", "loop_b", "mutual_inductance_h"})
        a, b = identities.get(_id(row["loop_a"])), identities.get(_id(row["loop_b"]))
        if a is None or b is None or a == b or tuple(sorted((a, b))) in pairs:
            raise ValueError("Mutual terms require a unique known pair of distinct loops.")
        value = row["mutual_inductance_h"]
        if type(value) not in (float, int) or not math.isfinite(value):
            raise ValueError("Mutual inductance must be finite and signed in henries.")
        pairs.add(tuple(sorted((a, b))))
        matrix[a, b] = matrix[b, a] = value
    scale = np.sqrt(np.diag(matrix))
    minimum_energy = float(np.linalg.eigvalsh(matrix / np.outer(scale, scale)).min())
    if minimum_energy < -1e-12:
        raise ValueError("Mutual inductances create a non-passive magnetic energy matrix.")
    frequencies = raw["frequency_hz"]
    if not isinstance(frequencies, list) or not 1 <= len(frequencies) <= 4096 or len(frequencies) * len(loops)**3 > 100_000_000:
        raise ValueError("Frequency sweep exceeds the bounded dense EM work budget.")
    frequencies = [_number(f, "frequency_hz", positive=True) for f in frequencies]
    if any(b <= a for a, b in zip(frequencies, frequencies[1:])):
        raise ValueError("Frequencies must increase strictly.")
    drive = np.asarray(voltages)
    results = []
    for frequency in frequencies:
        impedance = np.diag(resistance).astype(complex) + 2j * np.pi * frequency * matrix
        condition = float(np.linalg.cond(impedance))
        if not math.isfinite(condition) or condition > 1e12:
            raise ValueError("EM impedance matrix exceeds conditioning limit 1e12.")
        current = np.linalg.solve(impedance, drive)
        error = impedance @ current - drive
        relative = float(np.linalg.norm(error) / max(np.linalg.norm(drive), 1e-30))
        if not np.isfinite(current).all() or relative > 1e-9:
            raise ValueError("EM linear solve failed its residual check.")
        loss = np.abs(current)**2 * resistance
        source_power = float(np.real(np.vdot(current, drive)))
        results.append({"frequency_hz": frequency, "loops": [
            {"loop_id": row["loop_id"], loop_owners[i][0]: loop_owners[i][1],
             "current_real_a": float(current[i].real), "current_imag_a": float(current[i].imag),
             "current_magnitude_a": float(abs(current[i])),
             "loss_w": float(loss[i])} for i, row in enumerate(loops)],
            "source_real_power_w": source_power, "total_loss_w": float(loss.sum()),
            "power_balance_residual_w": source_power - float(loss.sum()),
            "relative_linear_residual": relative, "condition_number": condition})
    return {"contract": RESULT_CONTRACT, "status": "completed", "model_status": "experimental",
            "excluded_hierarchy_part_ids": excluded_parts,
            "production_qualified": False, "assembly_digest": assembly_physics_digest(raw["assembly"]),
            "request_digest": canonical_json_digest(raw), "coupling_included": any(
                matrix[a, b] != 0 and loop_owners[a] != loop_owners[b] for a, b in pairs),
            "field_coupling_executed": False, "minimum_normalized_energy_eigenvalue": minimum_energy,
            "samples": results, "limitations": ["Explicit lumped quasi-static magnetic RL loops only; RMS phasors.",
            "No radiation, electric-field coupling, shielding extraction, frequency-dependent loss, or EMI compliance.",
            "Mutual inductances must come from a measured/extracted model for this placement; board motion requires a new model."]}
