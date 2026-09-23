# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
import unittest
import tempfile
import json
import hashlib
from pathlib import Path
from python.spike_core.openfoam_buoyancy import validate_density_model,density_at_temperature,render_buoyancy_observers,validate_buoyancy_runtime
from python.spike_core.openfoam_multiregion import _material,_thermophysical_properties


def model():
    return {"type":"Boussinesq","rho0_kg_m3":1.2,"T0_k":298.15,"beta_per_k":1/298.15,
            "temperature_min_k":290.,"temperature_max_k":315.}


class BuoyancyTests(unittest.TestCase):
    def test_analytical_density_and_envelope(self):
        m=validate_density_model(model(),1.2)
        self.assertEqual(density_at_temperature(m,298.15),1.2)
        self.assertAlmostEqual(density_at_temperature(m,300.),1.2*(1-(300.-298.15)/298.15))
        self.assertGreater(density_at_temperature(m,290.),density_at_temperature(m,315.))
        with self.assertRaises(ValueError):density_at_temperature(m,316.)

    def test_admission_rejects_nonphysical_or_unknown(self):
        for key,value in (("beta_per_k",True),("rho0_kg_m3",1.3),("temperature_max_k",500.),
                          ("temperature_min_k",300.),("extra",0),("T0_k",float("nan"))):
            m=model();m[key]=value
            with self.assertRaises(ValueError):validate_density_model(m,1.2)

    def test_material_render_and_observer(self):
        raw={"id":"air","phase":"fluid","density_kg_m3":1.2,"conductivity_w_mk":.026,
             "specific_heat_j_kgk":1006.,"dynamic_viscosity_pa_s":1.8e-5}
        self.assertIn("equationOfState rhoConst;",_thermophysical_properties(_material(raw)))
        raw["density_model"]=model();material=_material(raw)
        text=_thermophysical_properties(material)
        self.assertIn("equationOfState Boussinesq;",text)
        self.assertIn("rho0 1.2;",text)
        observer=render_buoyancy_observers({"materials":[material],"regions":[{"id":"air","material_id":"air"}],
            "environment":{"ambient_temperature_k":298.15}})
        self.assertIn("fields (T rho);",observer)
        self.assertIn("operation min;",observer)
        self.assertIn("operation max;",observer)
        raw["phase"]="solid"
        with self.assertRaises(ValueError):_material(raw)

    def test_boundary_temperature_rejection(self):
        case={"materials":[{"id":"air","density_model":model()}],"regions":[{"id":"air","material_id":"air"}],
              "environment":{"ambient_temperature_k":298.15},"fans":[{"fluid_region_id":"air","inlet_temperature_k":400.}]}
        with self.assertRaises(ValueError):render_buoyancy_observers(case)
        case["fans"]=[];case["environment"]["pressure_outlets"]=[{"fluid_region_id":"air","backflow_temperature_k":100.}]
        with self.assertRaises(ValueError):render_buoyancy_observers(case)

    def test_runtime_interval_missing_negative_and_tamper(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            case={"materials":[{"id":"air","density_model":model()}],"regions":[{"id":"air","material_id":"air"}],
                  "numerics":{"delta_t_s":.1,"end_time_s":.3}}
            payload=json.dumps(case).encode();(root/"spike_multiregion_case.json").write_bytes(payload)
            manifest={"input_files":{"spike_multiregion_case.json":hashlib.sha256(payload).hexdigest()}}
            paths=[]
            for operation in ("min","max"):
                path=root/"postProcessing/air"/f"spikeBuoyancy{operation}_air"/"0/volFieldValue.dat"
                path.parent.mkdir(parents=True);path.write_text(".1 298.15 1.2\n.2 298.15 1.2\n.3 298.15 1.2\n")
                paths.append(path)
            evidence=validate_buoyancy_runtime(root,manifest)
            self.assertTrue(evidence["air"]["every_step_interval_passed"])
            for text in (".1 298.15 1.2\n.3 298.15 1.2\n", ".1 400 1.2\n.2 400 1.2\n.3 400 1.2\n", ".1 298.15 -1\n.2 298.15 -1\n.3 298.15 -1\n", ".1 298.15 50\n.2 298.15 50\n.3 298.15 50\n"):
                for path in paths:path.write_text(text)
                with self.assertRaises(ValueError):validate_buoyancy_runtime(root,manifest)
            (root/"spike_multiregion_case.json").write_text("{}")
            with self.assertRaises(ValueError):validate_buoyancy_runtime(root,manifest)
