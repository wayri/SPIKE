# SPDX-License-Identifier: Apache-2.0
"""Independent numerical checks used by the curated Raspberry Pi assembly."""
import copy
import hashlib
import math
import tempfile
import unittest
from pathlib import Path

from python.spike_core.contracts import SpiDeR
from python.spike_core.project_package import write_spike_package
from python.spike_core.spider_v2 import SpiDeRV2
from scripts.build_rpi_hat_acceptance import _acceptance, _verify_packaged_board_sources


def fixture():
    frequencies = [1e3, 1e7]
    signal = {"real": [], "imaginary": []}
    ground = {"real": [0.0, 0.0], "imaginary": [0.0, 0.0]}
    for frequency in frequencies:
        omega = 2 * math.pi * frequency
        signal_path = complex(.025, omega * 6e-9)
        ground_path = complex(.012, omega * 3e-9)
        bias_return = complex(2e6 + .012, omega * 3e-9)
        return_path = ground_path * bias_return / (ground_path + bias_return)
        value = 4700 / (4700 + signal_path + return_path)
        signal["real"].append(value.real); signal["imaginary"].append(value.imag)
    power = (5 / (12.5 + .012 + .012))**2 * 12.5
    return {
        "pi": {"element_map": {"sailor-hat": {"hat-load": "load"}},
               "native_result": {"data": {"element_power_w": {"load": power}}}},
        "si": {"node_map": {"sailor-hat": {"J501:3": "signal", "J501:6": "return"}},
               "native_result": {"data": {"frequency_hz": frequencies,
                   "node_voltage_v": {"signal": signal, "return": ground}}}},
        "thermal": {"summary": {"energy_balance_residual_w": 1e-12}},
    }


class RaspberryPiHatAcceptanceTests(unittest.TestCase):
    def test_each_occurrence_reads_exact_packaged_source_through_worker(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2] / "build") as directory:
            root = Path(directory)
            sources = {
                "base": b'(kicad_pcb (version 20240108) (net 0 "BASE"))',
                "hat": b'(kicad_pcb\r\n (version 20240108) (net 0 "HAT"))',
            }
            designs = []
            board_sources = {}
            design_ids = {}
            for board_id, source_bytes in sources.items():
                path = root / f"{board_id}.kicad_pcb"
                path.write_bytes(source_bytes)
                board_sources[board_id] = path
                design = SpiDeRV2.from_v1(SpiDeR(
                    design_id=board_id, name=board_id, source_format="kicad_pcb",
                    layers=[{"id": 0, "name": "F.Cu"}],
                    metadata={"source_sha256": hashlib.sha256(source_bytes).hexdigest()},
                )).to_dict()
                design["source"]["artifact_path"] = (
                    f"package:sources/{hashlib.sha256(source_bytes).hexdigest()}.kicad_pcb"
                )
                design_ids[board_id] = design["design_id"]
                designs.append(design)
            boards = [{"id": board_id, "design_id": design_ids[board_id],
                       "frame": {"frame_id": f"{board_id}-frame"}} for board_id in sources]
            project = root / "assembly.spike"
            write_spike_package(project, {
                "project": {"id": "rpi-source-fixture"}, "design_ir": designs[0],
                "assembly_ir": {"contract": "spike/assembly-ir/v1", "assembly_id": "assembly",
                                "name": "Assembly", "boards": boards},
                "assembly_designs": {"contract": "spike/assembly-designs/v1",
                                     "active_design_id": designs[0]["design_id"], "designs": designs},
            }, source_artifacts={path.name: path.read_bytes() for path in board_sources.values()})
            _verify_packaged_board_sources(project, board_sources)

    def test_independent_pi_si_thermal_oracles_pass(self):
        evidence = _acceptance(fixture())
        self.assertTrue(evidence["passed"])
        self.assertLess(evidence["si"]["max_complex_voltage_error_v"], 1e-14)

    def test_si_regression_fails_closed(self):
        results = copy.deepcopy(fixture())
        results["si"]["native_result"]["data"]["node_voltage_v"]["signal"]["real"][1] -= .01
        with self.assertRaisesRegex(ValueError, "numerical acceptance failed"):
            _acceptance(results)


if __name__ == "__main__":
    unittest.main()
