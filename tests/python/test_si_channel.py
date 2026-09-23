import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from jsonschema import Draft202012Validator

from python.spike_core.design_ir_v2 import (
    DesignIRV2, Layer, Material, Net, SourceIdentity, Track, Via, Zone,
)
from python.spike_core.si_channel import (
    REQUEST_CONTRACT,
    SiChannelError,
    analyze_uniform_design_channel,
    extract_uniform_path_rlgc,
    normalized_nrz_eye,
    time_domain_report,
    uniform_rlgc_network,
)
from python.spike_core.si_coupled_channel import (
    analyze_coupled_design_channel,
    extract_coupled_path_rlgc,
)
from python.spike_core.cli import main as cli_main
from python.spike_core.service import handle


class SiUniformChannelTests(unittest.TestCase):
    def design(self) -> DesignIRV2:
        copper = Material(
            id="material-copper", name="Copper", material_class="conductor",
            conductivity_s_per_m=5.8e7,
        )
        dielectric = Material(
            id="material-fr4", name="Fixture dielectric", material_class="dielectric",
            relative_permittivity=4.0, loss_tangent=0.015,
        )
        signal = Net(id="net-signal", name="SIG")
        ground = Net(id="net-ground", name="GND")
        return DesignIRV2(
            design_id="uniform-channel-fixture",
            name="uniform channel fixture",
            source=SourceIdentity(source_format="fixture", source_digest="a" * 64),
            materials=[copper, dielectric],
            layers=[
                Layer(id="layer-signal", name="F.Cu", layer_type="copper", order=0, z_mm=0.0,
                      thickness_mm=0.035, material_id=copper.id),
                Layer(id="layer-dielectric", name="Core", layer_type="dielectric", order=1, z_mm=0.035,
                      thickness_mm=0.2, material_id=dielectric.id),
                Layer(id="layer-reference", name="In1.Cu", layer_type="copper", order=2, z_mm=0.235,
                      thickness_mm=0.035, material_id=copper.id),
            ],
            nets=[signal, ground],
            tracks=[
                Track(id="track-1", net_id=signal.id, layer_id="layer-signal",
                      start_mm=(0.0, 0.0), end_mm=(50.0, 0.0), width_mm=0.35),
            ],
            zones=[
                Zone(id="zone-reference", net_id=ground.id, layer_ids=["layer-reference"],
                     outlines_mm=[[(-5.0, -5.0), (55.0, -5.0), (55.0, 5.0), (-5.0, 5.0)]]),
            ],
        )

    def request(self) -> dict:
        return {
            "contract": REQUEST_CONTRACT,
            "channel_id": "channel-1",
            "signal_net": "SIG",
            "reference_net": "GND",
            "reference_layer": "In1.Cu",
            "reference_impedance_ohm": 50.0,
            "frequencies_hz": np.linspace(0.0, 4.0e9, 1025).tolist(),
            "bit_rate_hz": 1.0e9,
            "bit_count": 512,
            "trace_limit": 128,
        }

    def coupled_design(self) -> DesignIRV2:
        design = self.design()
        victim = Net(id="net-victim", name="VICTIM")
        design.nets.append(victim)
        design.tracks.append(Track(
            id="track-victim", net_id=victim.id, layer_id="layer-signal",
            start_mm=(0.0, 0.8), end_mm=(50.0, 0.8), width_mm=0.35,
        ))
        return design

    def coupled_request(self) -> dict:
        request = self.request()
        request.update({
            "victim_net": "VICTIM",
            "frequencies_hz": np.linspace(0.0, 4.0e9, 257).tolist(),
            "cross_section_vertical_cells": 12,
            "trace_limit": 64,
        })
        request.pop("bit_rate_hz")
        request.pop("bit_count")
        return request

    def test_designir_path_produces_bounded_geometry_derived_channel(self) -> None:
        result = analyze_uniform_design_channel(self.design(), self.request())
        self.assertEqual(result["contract"], "spike/si-channel-result/v1")
        self.assertEqual(result["model_status"], "experimental")
        self.assertFalse(result["production_qualified"])
        extraction = result["extraction"]
        self.assertTrue(extraction["geometry"]["uniform_cross_section_verified"])
        self.assertTrue(extraction["geometry"]["reference_zone_full_path_coverage_verified"])
        self.assertTrue(extraction["qualification"]["execution_ready"])
        self.assertFalse(extraction["qualification"]["solver_ready"])
        self.assertAlmostEqual(extraction["geometry"]["length_m"], 0.05)
        self.assertGreater(extraction["rlgc_per_m"]["capacitance_f_per_m"], 0.0)
        self.assertEqual(result["network"]["port_count"], 2)
        self.assertEqual(result["time_domain"]["processing"]["window"], "none")
        self.assertEqual(result["eye"]["model_status"], "experimental")
        self.assertIn("ideal normalized NRZ source", result["eye"]["limitations"][0])
        self.assertGreater(result["resource_admission"]["estimated_numeric_bytes"], 0)

    def test_lossless_matched_line_has_zero_reflection_and_analytic_delay(self) -> None:
        capacitance = 100e-12
        inductance = 250e-9
        extraction = {
            "geometry": {"design_id": "analytic", "length_m": 1.0},
            "geometry_digest": "b" * 64,
            "rlgc_per_m": {
                "resistance_ohm_per_m": 0.0,
                "inductance_h_per_m": inductance,
                "capacitance_f_per_m": capacitance,
                "loss_tangent": 0.0,
            },
        }
        frequencies = np.linspace(0.0, 2.0e9, 2049)
        network = uniform_rlgc_network(extraction, frequencies, 50.0)
        s = network.s_parameters()
        np.testing.assert_allclose(s[:, 0, 0], 0.0, atol=1e-12)
        np.testing.assert_allclose(np.abs(s[:, 1, 0]), 1.0, atol=1e-12)
        delay = np.sqrt(inductance * capacitance)
        expected = np.exp(-1j * 2.0 * np.pi * frequencies * delay)
        np.testing.assert_allclose(s[:, 1, 0], expected, rtol=1e-11, atol=1e-11)
        time = time_domain_report(network)
        self.assertTrue(all(abs(point["impedance_ohm"] - 50.0) < 1e-10 for point in time["tdr"]))

    def test_normalized_eye_is_deterministic_and_explicitly_not_ber_qualification(self) -> None:
        extraction = {
            "geometry": {"design_id": "analytic", "length_m": 0.1},
            "geometry_digest": "c" * 64,
            "rlgc_per_m": {
                "resistance_ohm_per_m": 0.0,
                "inductance_h_per_m": 250e-9,
                "capacitance_f_per_m": 100e-12,
                "loss_tangent": 0.0,
            },
        }
        network = uniform_rlgc_network(extraction, np.linspace(0.0, 8.0e9, 4097), 50.0)
        first = normalized_nrz_eye(network, bit_rate_hz=1.0e9, bit_count=512)
        second = normalized_nrz_eye(network, bit_rate_hz=1.0e9, bit_count=512)
        self.assertEqual(first, second)
        self.assertGreater(first["eye_height_normalized"], 0.9)
        self.assertIn("not a protocol", first["limitations"][1])

    def test_explicit_noise_and_jitter_produce_reproducible_statistical_bathtub(self) -> None:
        request = self.request()
        request["statistical_eye_model"] = {
            "voltage_noise_rms_normalized": 0.08,
            "random_jitter_rms_s": 1.0e-11,
            "deterministic_jitter_pp_s": 2.0e-11,
            "decision_threshold_normalized": 0.0,
            "phase_bins": 33,
            "target_ber": 1.0e-6,
        }
        first = analyze_uniform_design_channel(self.design(), request)["eye"]["statistical"]
        second = analyze_uniform_design_channel(self.design(), request)["eye"]["statistical"]
        self.assertEqual(first, second)
        self.assertEqual(first["contract"], "spike/si-statistical-nrz-eye/v1")
        self.assertFalse(first["production_qualified"])
        self.assertEqual(first["compliance_status"], "not_evaluated")
        self.assertEqual(len(first["bathtub"]), 33)
        self.assertGreater(first["eye_width_at_target_ber_ui"], 0.0)
        self.assertGreater(first["integration"]["evaluations"], 1_000_000)
        self.assertIn("explicit user inputs", first["limitations"][2])

    def test_explicit_pam4_equalization_and_phase_search_are_bounded(self) -> None:
        request = self.request()
        request.pop("bit_rate_hz")
        request.pop("bit_count")
        request["symbol_rate_hz"] = 1.0e9
        request["symbol_count"] = 512
        request["pam4_model"] = {
            "tx_ffe_taps": [1.0],
            "rx_ctle_dc_gain": 1.0,
            "rx_dfe_taps": [0.0],
            "voltage_noise_rms_normalized": 0.01,
            "phase_bins": 17,
            "target_ber": 1.0e-6,
            "cdr_mode": "ideal_phase_search",
        }
        result = analyze_uniform_design_channel(self.design(), request)
        pam4 = result["eye"]["pam4"]
        self.assertEqual(pam4["contract"], "spike/si-pam4-eye/v1")
        self.assertFalse(pam4["production_qualified"])
        self.assertEqual(len(pam4["eye_heights_normalized"]), 3)
        self.assertEqual(len(pam4["bathtub"]), 17)
        self.assertEqual(pam4["equalization"]["dfe_mode"], "ideal_training_with_known_prior_symbols")
        self.assertIn("not rare-event simulation", pam4["limitations"][3])

    def test_nonuniform_or_discontinuous_geometry_fails_closed(self) -> None:
        bent = self.design()
        bent.tracks.append(Track(
            id="track-2", net_id="net-signal", layer_id="layer-signal",
            start_mm=(50.0, 0.0), end_mm=(50.0, 10.0), width_mm=0.35,
        ))
        with self.assertRaisesRegex(SiChannelError, "straight path"):
            extract_uniform_path_rlgc(bent, self.request())

        via = self.design()
        via.vias.append(Via(
            id="via-1", net_id="net-signal", center_mm=(25.0, 0.0), diameter_mm=0.6,
            drill_mm=0.3, start_layer_id="layer-signal", end_layer_id="layer-reference",
        ))
        with self.assertRaisesRegex(SiChannelError, "Vias"):
            extract_uniform_path_rlgc(via, self.request())

    def test_piecewise_planar_single_line_is_opt_in_and_records_bends(self) -> None:
        design = self.design()
        design.zones[0].outlines_mm = [[(-5.0, -5.0), (55.0, -5.0), (55.0, 30.0), (-5.0, 30.0)]]
        design.tracks[0].end_mm = (25.0, 0.0)
        design.tracks.append(Track(
            id="track-2", net_id="net-signal", layer_id="layer-signal",
            start_mm=(25.0, 0.0), end_mm=(25.0, 25.0), width_mm=0.35,
        ))
        request = self.request()
        request["path_mode"] = "piecewise_planar"
        result = analyze_uniform_design_channel(design, request)
        geometry = result["extraction"]["geometry"]
        self.assertEqual(geometry["path_mode"], "piecewise_planar")
        self.assertFalse(geometry["straight_path_verified"])
        self.assertTrue(geometry["piecewise_planar_path_verified"])
        self.assertEqual(len(geometry["bend_evidence"]), 1)
        self.assertIn("bend discontinuities", result["extraction"]["limitations"][-1])

    def test_runtime_request_keys_and_coupled_piecewise_tolerances_fail_closed(self) -> None:
        request = self.request()
        request["unreviewed_control"] = True
        with self.assertRaisesRegex(SiChannelError, "unknown fields"):
            analyze_uniform_design_channel(self.design(), request)

        request = self.coupled_request()
        request["path_mode"] = "piecewise_planar"
        with self.assertRaisesRegex(SiChannelError, "coupled_separation_tolerance_mm"):
            analyze_uniform_design_channel(self.coupled_design(), request)

    def test_frequency_grid_requires_dc_and_uniform_spacing(self) -> None:
        extraction = {
            "geometry": {"length_m": 1.0},
            "rlgc_per_m": {
                "resistance_ohm_per_m": 0.0,
                "inductance_h_per_m": 250e-9,
                "capacitance_f_per_m": 100e-12,
                "loss_tangent": 0.0,
            },
        }
        with self.assertRaisesRegex(SiChannelError, "start at DC"):
            uniform_rlgc_network(extraction, [1.0, 2.0, 3.0], 50.0)
        with self.assertRaisesRegex(SiChannelError, "uniform frequency"):
            uniform_rlgc_network(extraction, [0.0, 1.0, 3.0], 50.0)

    def test_reference_zone_must_cover_the_complete_trace_footprint(self) -> None:
        design = self.design()
        design.zones[0].outlines_mm = [[(0.0, -0.1), (50.0, -0.1), (50.0, 0.1), (0.0, 0.1)]]
        with self.assertRaisesRegex(SiChannelError, "not fully covered"):
            extract_uniform_path_rlgc(design, self.request())

    def test_coupled_geometry_produces_four_port_s_next_and_fext(self) -> None:
        result = analyze_coupled_design_channel(self.coupled_design(), self.coupled_request())
        extraction = result["extraction"]
        capacitance = np.asarray(extraction["rlgc_per_m"]["capacitance_f_per_m"])
        self.assertEqual(capacitance.shape, (2, 2))
        self.assertLess(capacitance[0, 1], 0.0)
        self.assertGreater(np.min(np.linalg.eigvalsh(capacitance)), 0.0)
        self.assertEqual(result["network"]["port_count"], 4)
        self.assertEqual(
            result["network"]["port_order"],
            ["aggressor.near", "victim.near", "aggressor.far", "victim.far"],
        )
        self.assertEqual(result["network"]["checks"]["passivity"]["status"], "pass")
        self.assertEqual(result["network"]["checks"]["reciprocity"]["status"], "pass")
        self.assertTrue(result["crosstalk"]["geometry_or_field_coupling_claimed"])
        self.assertTrue(np.isfinite(result["crosstalk"]["next"]["worst_transfer_db"]))
        self.assertTrue(np.isfinite(result["crosstalk"]["fext"]["worst_transfer_db"]))
        self.assertFalse(result["production_qualified"])

        worker = handle({
            "id": "si-coupled-test",
            "method": "run_si_uniform_channel",
            "params": {"design": self.coupled_design().to_dict(), "request": self.coupled_request()},
        })
        self.assertTrue(worker["ok"], worker)
        self.assertEqual(worker["result"]["network"]["port_count"], 4)

    def test_coupled_geometry_rejects_longitudinal_skew_and_cancellation(self) -> None:
        design = self.coupled_design()
        design.tracks[-1].end_mm = (45.0, 0.8)
        with self.assertRaisesRegex(SiChannelError, "coextensive"):
            extract_coupled_path_rlgc(design, self.coupled_request())
        with self.assertRaisesRegex(SiChannelError, "cancelled"):
            extract_coupled_path_rlgc(
                self.coupled_design(), self.coupled_request(), cancel_check=lambda: True,
            )

    def test_piecewise_coupled_differential_result_uses_mixed_mode_subnetwork(self) -> None:
        design = self.coupled_design()
        design.zones[0].outlines_mm = [[(-5.0, -5.0), (55.0, -5.0), (55.0, 30.0), (-5.0, 30.0)]]
        design.tracks[0].end_mm = (25.0, 0.0)
        design.tracks[-1].end_mm = (24.2, 0.8)
        design.tracks.extend([
            Track(id="track-signal-bend", net_id="net-signal", layer_id="layer-signal",
                  start_mm=(25.0, 0.0), end_mm=(25.0, 20.0), width_mm=0.35),
            Track(id="track-victim-bend", net_id="net-victim", layer_id="layer-signal",
                  start_mm=(24.2, 0.8), end_mm=(24.2, 20.0), width_mm=0.35),
        ])
        request = self.coupled_request()
        request.update({
            "path_mode": "piecewise_planar",
            "coupled_separation_tolerance_mm": 0.01,
            "coupled_skew_tolerance_mm": 2.0,
            "signaling": "differential",
            "bit_rate_hz": 1.0e9,
            "bit_count": 256,
        })
        result = analyze_uniform_design_channel(design, request)
        self.assertEqual(result["extraction"]["geometry"]["path_mode"], "piecewise_planar")
        self.assertTrue(result["extraction"]["geometry"]["piecewise_parallel_pair_verified"])
        differential = result["differential"]
        self.assertIsNotNone(differential)
        self.assertEqual(differential["transform"]["differential_subnetwork_ports"], ["differential.near", "differential.far"])
        self.assertEqual(result["time_domain"], differential["time_domain"])
        self.assertEqual(result["eye"], differential["eye"])
        self.assertFalse(differential["production_qualified"])

    def test_eye_cancellation_is_fail_closed(self) -> None:
        extraction = {
            "geometry": {"design_id": "analytic", "length_m": 0.1},
            "geometry_digest": "d" * 64,
            "rlgc_per_m": {
                "resistance_ohm_per_m": 0.0,
                "inductance_h_per_m": 250e-9,
                "capacitance_f_per_m": 100e-12,
                "loss_tangent": 0.0,
            },
        }
        network = uniform_rlgc_network(extraction, np.linspace(0.0, 8.0e9, 4097), 50.0)
        with self.assertRaisesRegex(SiChannelError, "cancelled"):
            normalized_nrz_eye(
                network, bit_rate_hz=1.0e9, bit_count=512, cancel_check=lambda: True,
            )

    def test_worker_cli_and_registered_schemas_preserve_experimental_boundary(self) -> None:
        design = self.design()
        request = self.request()
        worker = handle({
            "id": "si-channel-test",
            "method": "run_si_uniform_channel",
            "params": {"design": design.to_dict(), "request": request},
        })
        self.assertTrue(worker["ok"], worker)
        result = worker["result"]
        self.assertFalse(result["production_qualified"])
        schema_root = Path(__file__).resolve().parents[2] / "schemas"
        catalog = json.loads((schema_root / "manifest.json").read_text(encoding="utf-8"))
        request_schema = json.loads((schema_root / catalog["schemas"][REQUEST_CONTRACT]).read_text(encoding="utf-8"))
        result_schema = json.loads((schema_root / catalog["schemas"][result["contract"]]).read_text(encoding="utf-8"))
        Draft202012Validator(request_schema).validate(request)
        Draft202012Validator(result_schema).validate(result)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            design_path = root / "design.json"
            request_path = root / "request.json"
            output_path = root / "result.json"
            design_path.write_text(json.dumps(design.to_dict()), encoding="utf-8")
            request_path.write_text(json.dumps(request), encoding="utf-8")
            exit_code = cli_main([
                "--output", str(output_path), "--quiet", "si-geometry-channel",
                str(design_path), str(request_path),
            ])
            self.assertEqual(exit_code, 0)
            cli_result = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(cli_result["provenance"]["request_digest"], result["provenance"]["request_digest"])


if __name__ == "__main__":
    unittest.main()
