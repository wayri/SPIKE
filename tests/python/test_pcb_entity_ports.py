# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from python.spike_core.pcb_entity_ports import (
    CONTRACT, compile_entity_ports, prepare_entity_port_case, validate_entity_port_binding,
)
from python.spike_core.external_engines import ExternalEngineDescriptor, run_openems_case
from tests.python.test_openems_far_field import far_field_design, far_field_spec, far_field_request


def request():
    return {"contract": CONTRACT, "ports": [{"id": "feed",
        "signal": {"entity_id": "rf", "layer": "F.Cu", "at_mm": [10, 0]},
        "reference": {"entity_id": "gnd", "layer": "F.Cu", "at_mm": [10, 2]},
        "impedance_ohm": 50, "excite": True}]}


class EntityPortTests(unittest.TestCase):
    def setUp(self):
        self.design = far_field_design()
        self.spec = far_field_spec(far_field_request())

    def test_compile_preserves_inputs_farfield_and_mapping(self):
        before = copy.deepcopy((self.design, self.spec))
        compiled = compile_entity_ports(self.design, self.spec, request())
        self.assertEqual(before, (self.design, self.spec))
        self.assertEqual(compiled.options["ports"], [{"start": [10., 2., 0.],
            "stop": [10., 0., 0.], "direction": "y", "impedance_ohm": 50., "excite": True}])
        self.assertEqual(compiled.options["far_field"], self.spec.options["far_field"])
        self.assertEqual(validate_entity_port_binding(self.design, compiled), [])

    def test_source_identity_not_merely_same_net(self):
        self.design.tracks.append({**self.design.tracks[0], "id": "elsewhere",
                                   "start": [30, 0], "end": [50, 0]})
        req = request()
        req["ports"][0]["signal"]["entity_id"] = "elsewhere"
        with self.assertRaisesRegex(ValueError, "E_PORT_ATTACHMENT"):
            compile_entity_ports(self.design, self.spec, req)

    def test_stale_geometry_or_modified_ports_rejected(self):
        compiled = compile_entity_ports(self.design, self.spec, request())
        self.design.tracks[0]["width"] = 1.2
        self.assertTrue(validate_entity_port_binding(self.design, compiled))
        self.design.tracks[0]["width"] = 1
        compiled.options["ports"][0]["stop"][0] += .1
        self.assertTrue(validate_entity_port_binding(self.design, compiled))

    def test_round_track_endcap_is_not_exported(self):
        req = request()
        req["ports"][0]["signal"]["at_mm"] = [-.1, 0]
        req["ports"][0]["reference"]["at_mm"] = [-.1, 2]
        with self.assertRaisesRegex(ValueError, "exported track rectangle"):
            compile_entity_ports(self.design, self.spec, req)

    def test_unknown_duplicate_short_and_off_axis(self):
        for mode in ("unknown", "duplicate", "short", "diagonal", "unselected"):
            with self.subTest(mode=mode):
                design, req, spec = copy.deepcopy(self.design), request(), copy.deepcopy(self.spec)
                if mode == "unknown": req["ports"][0]["signal"]["entity_id"] = "missing"
                if mode == "duplicate": design.tracks.append(copy.deepcopy(design.tracks[0]))
                if mode == "short": req["ports"][0]["reference"] = copy.deepcopy(req["ports"][0]["signal"])
                if mode == "diagonal": req["ports"][0]["signal"]["at_mm"][0] = 11
                if mode == "unselected": spec.net_names = ["GND"]
                with self.assertRaises(ValueError): compile_entity_ports(design, spec, req)

    def test_strict_contract_and_numeric_values(self):
        for value in (True, "50", float("nan"), 10**400, -1):
            req = request()
            req["ports"][0]["impedance_ohm"] = value
            with self.assertRaises(ValueError): compile_entity_ports(self.design, self.spec, req)
        for req in ({}, {**request(), "shell": "ignored?"}, {"contract": CONTRACT, "ports": []}):
            with self.assertRaises(ValueError): compile_entity_ports(self.design, self.spec, req)

    def test_prepare_real_authenticated_case_and_reject_bound_mutation(self):
        ready = ExternalEngineDescriptor(id="external.openems", name="openEMS", role="test",
            license="GPL-3.0-or-later", homepage="https://docs.openems.de/", state="reference_validated")
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,
            {"SPIKE_STATE_HOME": str(Path(directory) / "state")}), patch(
            "python.spike_core.external_engines._openems_descriptor", return_value=ready):
            root = Path(directory) / "case"
            result = prepare_entity_port_case(self.design, self.spec, request(), output_dir=root)
            self.assertEqual(result["status"], "ready_to_run")
            job = json.loads((root / "job.json").read_text())
            self.assertEqual(job["analysis"]["options"]["entity_port_binding"]["request"], request())
            self.assertTrue(result["validation"]["far_field"]["enabled"])
            from python.spike_core.external_engines import _case_inputs
            normalized = json.loads((root / "geometry.json").read_text())
            rebuilt_design, rebuilt_spec = _case_inputs(job, normalized)
            self.assertEqual(validate_entity_port_binding(rebuilt_design, rebuilt_spec), [])
            compiled = compile_entity_ports(self.design, self.spec, request())
            self.design.tracks[0]["width"] = 1.2
            from python.spike_core.external_engines import prepare_openems_case
            blocked = prepare_openems_case(self.design, compiled, Path(directory) / "stale")
            self.assertEqual(blocked["status"], "blocked")
            self.assertFalse((Path(directory) / "stale").exists())


if __name__ == "__main__":
    unittest.main()
