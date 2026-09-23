# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
import unittest
import tempfile
import hashlib
from pathlib import Path
from python.spike_core.openfoam_flow_energy_validation import (integrate_energy_history,read_numeric_history,
    _verify_equation_scope,_verify_history_stability,_initial_region_storage)
from unittest.mock import patch


class FlowEnergyValidationTests(unittest.TestCase):
    def test_initial_storage_honors_reference_kinetic_and_pressure(self):
        def field(dim,value):
            return f"dimensions [{dim}];\ninternalField uniform {value};\n"
        texts={"constant/air/thermophysicalProperties":"Cp 2;\nrho 3;\nTref 300;\nHref 7;\nHf 999;\n",
            "0/air/T":field("0 0 0 1 0 0 0","310"),
            "0/air/U":field("0 1 -1 0 0 0 0","(3 4 0)"),
            "0/air/p":field("1 -1 -2 0 0 0 0","100"),
            "0/air/p_rgh":field("1 -1 -2 0 0 0 0","100")}
        region={"id":"air","kind":"fluid"};material={"specific_heat_j_kgk":2,"density_kg_m3":3}
        with tempfile.TemporaryDirectory() as directory, patch("python.spike_core.openfoam_flow_energy_validation._dictionary",side_effect=lambda root,manifest,relative:texts[relative]):
            root=Path(directory);manifest={"input_files":{}}
            result=_initial_region_storage(root,manifest,region,material,.2,True)
            self.assertEqual(result["sensible_enthalpy_j_kg"],27)
            self.assertEqual(result["kinetic_energy_j_kg"],12.5)
            self.assertAlmostEqual(result["storage_j"],3.7)
            without=_initial_region_storage(root,manifest,region,material,.2,False)
            self.assertAlmostEqual(without["storage_j"],23.7)
            texts["0/air/p_rgh"]=field("1 -1 -2 0 0 0 0","0")
            with self.assertRaisesRegex(ValueError,"must agree"):
                _initial_region_storage(root,manifest,region,material,.2,True)

    def test_first_step_failure_cannot_hide_behind_small_global_defect(self):
        result=integrate_energy_history([0,.001,10],[0,.000099, .999999],[0,0,0],.1,relative_tolerance=.001)
        self.assertLess(result["relative_residual"],.001)
        self.assertGreater(result["maximum_step_relative_residual"],.001)
        self.assertFalse(result["passed"])

    def test_euler_not_trapezoidal_and_signed_storage(self):
        # Input 10 W, outward 12 then 14 W: stored energy decreases 2 then 4 J.
        r=integrate_energy_history([1,2,3],[100,98,94],[0,12,14],10.)
        self.assertTrue(r["passed"])
        self.assertEqual(r["boundary_energy_j"],26)
        self.assertEqual(r["stored_energy_change_j"],-6)
        self.assertEqual(r["maximum_step_defect_j"],0)

    def test_fail_defect_missing_and_nonfinite(self):
        self.assertFalse(integrate_energy_history([1,2],[0,0],[0,0],1.)["passed"])
        # Opposite per-step errors must not disappear in the cumulative balance.
        cancelled=integrate_energy_history([1,2,3],[0,0,2],[0,0,0],1.)
        self.assertEqual(cancelled["relative_residual"],0)
        self.assertFalse(cancelled["passed"])
        for t,s,q in (([1,1],[0,1],[0,1]),([1,2],[0],[1,2]),([1,2],[0,float("nan")],[0,1])):
            with self.assertRaises(ValueError):integrate_energy_history(t,s,q,1.)

    def test_history_parse_and_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"data.dat"
            path.write_text("# Time field\n0.1 2\n0.2 3\n",encoding="ascii")
            values,digest=read_numeric_history(path,2)
            self.assertEqual(values.tolist(),[[.1,2],[.2,3]])
            self.assertEqual(len(digest),64)
            path.write_text(".1 nan\n.2 3\n",encoding="ascii")
            with self.assertRaises(ValueError):read_numeric_history(path,2)

    def test_hashed_equation_scope_and_dpdt_default(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            thermo=root/"constant/air/thermophysicalProperties"
            thermo.parent.mkdir(parents=True)
            turbulence=thermo.parent/"turbulenceProperties"
            base="equationOfState rhoConst;\nthermo hConst;\nenergy sensibleEnthalpy;\ntransport const;\n"
            manifest={"input_files":{}}
            case={"regions":[{"id":"air","kind":"fluid"}]}
            def write(path,text):
                path.write_text(text,encoding="ascii")
                manifest["input_files"][path.relative_to(root).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
            write(turbulence,"simulationType laminar;\n")
            write(thermo,base)
            _verify_equation_scope(root,manifest,case,True)
            with self.assertRaises(ValueError):_verify_equation_scope(root,manifest,case,False)
            write(thermo,base+"dpdt false;\n")
            _verify_equation_scope(root,manifest,case,False)
            with self.assertRaises(ValueError):_verify_equation_scope(root,manifest,case,True)
            write(thermo,base+"dpdt true;\ndpdt false;\n")
            with self.assertRaises(ValueError):_verify_equation_scope(root,manifest,case,True)
            write(thermo,base.replace("rhoConst","perfectGas"))
            with self.assertRaises(ValueError):_verify_equation_scope(root,manifest,case,True)
            write(thermo,base)
            write(turbulence,"simulationType RAS;\n")
            with self.assertRaises(ValueError):_verify_equation_scope(root,manifest,case,True)
            turbulence.write_text("simulationType laminar;\n",encoding="ascii")
            with self.assertRaises(ValueError):_verify_equation_scope(root,manifest,case,True)

    def test_history_modified_after_read_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();path=root/"trace.dat"
            path.write_text(".1 2\n.2 3\n",encoding="ascii")
            _,digest=read_numeric_history(path,2)
            _verify_history_stability(root,{"trace.dat":digest})
            path.write_text(".1 2\n.2 4\n",encoding="ascii")
            with self.assertRaises(ValueError):_verify_history_stability(root,{"trace.dat":digest})
