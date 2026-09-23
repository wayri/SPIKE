# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Synthetic evidence reader tests; these are not actual field qualifications."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from python.spike_core.crossboard_field_screen import screen_case,compare_mesh_cases
from python.spike_core.openems_assembly_geometry import compile_assembly_geometry
from tests.python.test_openems_assembly_geometry import fixture


def write_case(path,resolution=2.):
    path.mkdir();raw=fixture();compiled=compile_assembly_geometry(raw)
    result={"status":"executed","field_coupling_executed":True,"ports":["A.near","A.far","B.near","B.far"],
        "reference_impedance_ohm":50.,"frequency_hz":[1e8,2e8],"limitations":["Synthetic reader fixture, not field evidence."],
        "s_real":[[[0.]*4 for _ in range(4)] for _ in range(2)],
        "s_imag":[[[0.]*4 for _ in range(4)] for _ in range(2)],
        "meshes":[{"inner_pml_bounds_mm":[[-5,35],[-5,15],[-5,10]]} for _ in range(4)],
        "mesh_resolution_mm":resolution,"end_criteria":1e-7,"max_timesteps":120000}
    hashes={}
    for name,data in (("geometry.json",raw),("compiled.json",compiled),("field-result.json",result)):
        payload=json.dumps(data).encode();(path/name).write_bytes(payload);hashes[name]=hashlib.sha256(payload).hexdigest()
    (path/"execution.json").write_text(json.dumps({"status":"executed","sources_unchanged":True,"execution":{"returncode":0},"artifact_sha256":hashes}))
    (path/'solver.log').write_text(('Create FDTD operator\nExcitation signal length is: 20 timesteps\n'
        'Timestep: 100 || Energy: ~1e-9 (-80.00dB)\nTime for 100 iterations with 100 cells\n')*4)
    for i in range(4):
        case=path/f"excitation-{i}";(case/"simulation").mkdir(parents=True)
        (case/"geometry.xml").write_text(f'<ContinuousStructure><Excitation Name="port_excite_{i+1}" Excite="0,0,-1"/></ContinuousStructure>')
        for p in range(1,5):
            for kind in ("ut","it"):(case/"simulation"/f"port_{kind}_{p}").write_text("0 0\n1 0\n")


class FieldScreenTests(unittest.TestCase):
    def test_hash_bound_screen_and_three_mesh_comparison(self):
        with tempfile.TemporaryDirectory() as temp:
            paths=[Path(temp)/str(i) for i in range(3)]
            for p,r in zip(paths,(3.,2.,1.)):write_case(p,r)
            self.assertTrue(screen_case(paths[0])["screen_passed"])
            report=compare_mesh_cases(paths)
            self.assertTrue(report["screen_passed"]);self.assertFalse(report["production_qualified"])
            with self.assertRaises(ValueError):compare_mesh_cases(paths[:2])

    def test_incomplete_independent_column_and_hash_tamper(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"case";write_case(path)
            (path/"excitation-2/geometry.xml").write_text('<ContinuousStructure><Excitation Name="port_excite_1" Excite="0,0,-1"/></ContinuousStructure>')
            with self.assertRaisesRegex(ValueError,"identity"):screen_case(path)
            (path/"geometry.json").write_text("{}")
            with self.assertRaisesRegex(ValueError,"hash"):screen_case(path)

    def test_explicit_tolerances(self):
        for value in (0,True,float("nan"),float("inf")):
            with self.assertRaises(ValueError):screen_case("unused",passivity_excess=value)

    def test_moving_pml_cannot_pass_mesh_screen(self):
        with tempfile.TemporaryDirectory() as temp:
            paths=[Path(temp)/str(i) for i in range(3)]
            for p,r in zip(paths,(3.,2.,1.)):write_case(p,r)
            target=paths[1]/'field-result.json';raw=json.loads(target.read_text())
            for mesh in raw['meshes']:mesh['inner_pml_bounds_mm'][0][0]-=1
            target.write_text(json.dumps(raw))
            manifest=paths[1]/'execution.json';execution=json.loads(manifest.read_text())
            execution['artifact_sha256']['field-result.json']=hashlib.sha256(target.read_bytes()).hexdigest()
            manifest.write_text(json.dumps(execution))
            report=compare_mesh_cases(paths)
            self.assertFalse(report['fixed_physical_pml_interface'])
            self.assertFalse(report['screen_passed'])
