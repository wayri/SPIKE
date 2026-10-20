# SPDX-License-Identifier: Apache-2.0
"""Physical spatial-chain/RLC endpoint oracle, independent of wave feedback."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
import numpy as np
from scipy.linalg import expm
from numpy.polynomial.legendre import leggauss
from examples.rlgc_loaded_star.run_loaded import request
from python.spike_core import rlgc_loaded_star as loaded
from tests.python.test_rlgc_coupled_star import physical_oracle as wave_oracle, value


def physical_oracle(raw, index):
    model = {"legs": raw["legs"], "excitations": [{"frequency_hz": s["frequency_hz"]} for s in raw["sources"]]}
    count = len(raw["legs"])
    _, _, operators, lengths, coefficients = wave_oracle(model, index, incident=np.zeros(2*count))
    transfer = [expm(m*length) for m,length in zip(operators,lengths)]
    terms = sorted(raw["terminations"], key=lambda t:t["port"])
    omega = 2*np.pi*raw["sources"][index]["frequency_hz"]
    r,l,c = (np.array([t[key] for t in terms]) for key in ("resistance_ohm","inductance_h","capacitance_f"))
    zs,yc = r+1j*omega*l,1j*omega*c
    equations = np.zeros((4*count,4*count),complex)
    for k in range(count):
        p=slice(2*k,2*k+2)
        equations[p,4*k:4*k+4] = np.hstack([np.diag(1+zs[p]*yc[p]),np.diag(zs[p])])
    for k in range(1,count):
        rows=slice(2*count+2*(k-1),2*count+2*k)
        equations[rows,:4]=-transfer[0][:2]
        equations[rows,4*k:4*k+4]=transfer[k][:2]
    for k in range(count):equations[-2:,4*k:4*k+4]=transfer[k][2:]
    rhs=np.zeros(4*count,complex);rhs[:2*count]=[value(z) for z in raw["sources"][index]["voltage_v"]]
    initial=np.linalg.solve(equations,rhs)
    states=[initial[4*k:4*k+4] for k in range(count)]
    voltage=np.concatenate([state[:2] for state in states]);current=np.concatenate([state[2:] for state in states])
    return states,operators,lengths,coefficients,voltage,current,current+yc*voltage


class LoadedStarTests(unittest.TestCase):
    def test_cancellation_floor_is_roundoff_limited(self):
        compare = loaded.cascade.bound._same_vector
        for scale in (1e-3, 1., 1e3):
            zero = np.zeros(2, complex)
            near = np.array([np.finfo(float).eps*scale, 0.])
            with self.assertRaises(loaded.cascade.bound.TerminatedPairError): compare(near, zero)
            compare(near, zero, scale)
            with self.assertRaises(loaded.cascade.bound.TerminatedPairError): compare(np.array([1e-10*scale, 0.]), zero, scale)

    def test_physical_branch_endpoints_fields_heat_and_energy(self):
        raw = request(); before = deepcopy(raw); out = loaded.run_rlgc_loaded_star(raw)
        self.assertEqual(raw, before); self.assertEqual(out["source_request"], raw)
        for index, point in enumerate(out["points"]):
            states, operators, lengths, coefficients, voltage, current, source_current = physical_oracle(raw, index)
            for j, t in enumerate(point["terminals"]):
                for key, expected in (("voltage_v", voltage[j]), ("current_into_line_a", current[j]), ("source_current_a", source_current[j])):
                    np.testing.assert_allclose(value(t[key]), expected, atol=2e-11, rtol=2e-9)
                np.testing.assert_allclose(t["resistor_heat_w"], t["resistance_ohm"]*abs(source_current[j])**2, atol=2e-12, rtol=2e-9)
                np.testing.assert_allclose(value(t["source_power_va"]), value(raw["sources"][index]["voltage_v"][j])*np.conj(source_current[j]), atol=2e-12, rtol=2e-9)
                np.testing.assert_allclose(value(t["line_power_va"]), voltage[j]*np.conj(current[j]), atol=2e-12, rtol=2e-9)
                for key, expected in (("inductor_average_energy_j", .5*t["inductance_h"]*abs(source_current[j])**2),
                                      ("capacitor_average_energy_j", .5*t["capacitance_f"]*abs(voltage[j])**2)):
                    np.testing.assert_allclose(t[key], expected, atol=2e-20, rtol=2e-9)
            integrated = np.zeros(2)
            for k, leg in enumerate(out["star_result"]["legs"]):
                child = leg["result"]["points"][index]
                for probe in child["probe_values"]:
                    expected = expm(operators[k]*lengths[k]*probe["fractional_position"])@states[k]
                    actual = [value(c["voltage_v"]) for c in probe["conductors"]]+[value(c["current_left_to_right_a"]) for c in probe["conductors"]]
                    np.testing.assert_allclose(actual, expected, atol=2e-11, rtol=2e-9)
                estimates = []
                for order in (32, 64):
                    nodes, weights = leggauss(order); heat = np.zeros(2)
                    for node, weight in zip(nodes, weights):
                        state = expm(operators[k]*lengths[k]*(node+1)/2)@states[k]
                        heat += weight*lengths[k]/2*np.array([np.vdot(state[2:], coefficients[k][0]@state[2:]).real,
                                                              np.vdot(state[:2], coefficients[k][1]@state[:2]).real])
                    estimates.append(heat)
                np.testing.assert_allclose(estimates[0], estimates[1], atol=2e-12, rtol=2e-9)
                np.testing.assert_allclose([child["power_balance"][key] for key in ("conductor_loss_w", "dielectric_loss_w")], heat, atol=2e-12, rtol=2e-9)
                integrated += heat
            balance = point["power_balance"]
            np.testing.assert_allclose([balance["line_conductor_heat_w"], balance["line_dielectric_heat_w"]], integrated, atol=2e-12, rtol=2e-9)
            self.assertAlmostEqual(balance["total_heat_w"], sum(integrated)+balance["terminal_resistor_heat_w"], delta=2e-12)
        json.dumps(out, allow_nan=False); self.assertFalse(out["production_qualified"])

    def test_two_leg_equivalence_to_loaded_cascade(self):
        from python.spike_core.rlgc_loaded_cascade import run_rlgc_loaded_cascade, REQUEST
        raw=request();raw["legs"]=raw["legs"][:2];raw["terminations"]=raw["terminations"][:4]
        for source in raw["sources"]:source["voltage_v"]=source["voltage_v"][:4]
        expected=run_rlgc_loaded_cascade({"contract":REQUEST,"sections":raw["legs"],"terminations":raw["terminations"],"sources":raw["sources"]})
        actual=loaded.run_rlgc_loaded_star(raw)
        for a,b in zip(actual["points"],expected["points"]):
            for key in ("voltage_v","current_into_line_a","source_current_a"):
                np.testing.assert_allclose([value(t[key]) for t in a["terminals"]],[value(t[key]) for t in b["terminals"]],atol=2e-11,rtol=2e-9)
            self.assertAlmostEqual(a["power_balance"]["total_heat_w"],b["power_balance"]["total_heat_w"],delta=2e-12)

    def test_matched_resistive_sources_reproduce_prescribed_wave_star(self):
        raw=request();reference=raw["legs"][0]["pair"]["modes"]["even"]["reference_impedance_ohm"]
        for t in raw["terminations"]:t.update(resistance_ohm=reference,inductance_h=0.,capacitance_f=0.)
        expected_request={"contract":loaded.star.REQUEST,"legs":raw["legs"],"excitations":[{"frequency_hz":s["frequency_hz"],"incident_waves":[{"real":float(value(z).real/(2*np.sqrt(reference))),"imag":float(value(z).imag/(2*np.sqrt(reference)))} for z in s["voltage_v"]]} for s in raw["sources"]]}
        expected=loaded.star.run_rlgc_coupled_star(expected_request);actual=loaded.run_rlgc_loaded_star(raw)
        for a,b in zip(actual["points"],expected["points"]):
            np.testing.assert_allclose([value(t["voltage_v"]) for t in a["terminals"]],[value(t["voltage_v"]) for t in b["boundary_values"]],atol=2e-11,rtol=2e-9)
            self.assertAlmostEqual(a["power_balance"]["line_conductor_heat_w"],b["power_balance"]["conductor_loss_w"],delta=2e-12)
            self.assertAlmostEqual(a["power_balance"]["line_dielectric_heat_w"],b["power_balance"]["dielectric_loss_w"],delta=2e-12)

    def test_zero_scaling_record_order_leg_and_conductor_permutation(self):
        raw = request(); base = loaded.run_rlgc_loaded_star(raw)
        modified = deepcopy(raw); modified["terminations"].reverse()
        self.assertEqual(loaded.run_rlgc_loaded_star(modified)["points"], base["points"])
        for factor in (0, -2):
            modified = deepcopy(raw)
            for s in modified["sources"]:
                for z in s["voltage_v"]: z.update(real=factor*z["real"], imag=factor*z["imag"])
            actual = loaded.run_rlgc_loaded_star(modified)
            for a, b in zip(base["points"], actual["points"]):
                self.assertAlmostEqual(b["power_balance"]["total_heat_w"], factor**2*a["power_balance"]["total_heat_w"], delta=2e-12)
        for permutation, reverse in (([1, 0, 3, 2, 5, 4], False), ([4, 5, 0, 1, 2, 3], True)):
            modified = deepcopy(raw)
            if reverse: modified["legs"] = [modified["legs"][k] for k in (2,0,1)]
            else:
                for s in modified["legs"]: s["pair"]["conductor_ids"].reverse()
            for s in modified["sources"]: s["voltage_v"] = [s["voltage_v"][i] for i in permutation]
            modified["terminations"] = [{**raw["terminations"][port], "port": j} for j, port in enumerate(permutation)]
            actual = loaded.run_rlgc_loaded_star(modified)
            for a, b in zip(base["points"], actual["points"]):
                for j, port in enumerate(permutation):
                    np.testing.assert_allclose(value(b["terminals"][j]["voltage_v"]), value(a["terminals"][port]["voltage_v"]), atol=2e-11, rtol=2e-9)
                self.assertAlmostEqual(a["power_balance"]["total_heat_w"], b["power_balance"]["total_heat_w"], delta=2e-12)

    def test_large_storage_and_absorbing_source_keep_j_var_w_separate(self):
        raw = request()
        for leg in raw["legs"]:
            for mode in leg["pair"]["modes"].values(): mode["samples"] = [{"frequency_hz": 1000., "resistance_ohm_per_m": 0., "conductance_s_per_m": 0.}]
            leg["pair"]["modes"]["odd"] = deepcopy(leg["pair"]["modes"]["even"])
        raw["sources"] = [{"frequency_hz": 1000., "voltage_v": [{"real": v, "imag": 0.} for v in (1, 0, 2, 0, 3, 0)]}]
        for t in raw["terminations"]: t.update(resistance_ohm=50., inductance_h=1e-3, capacitance_f=1e-4)
        point = loaded.run_rlgc_loaded_star(raw)["points"][0]; budget = point["power_balance"]
        self.assertGreater(budget["terminal_capacitor_average_energy_j"], 1e-8)
        self.assertAlmostEqual(budget["total_heat_w"], budget["terminal_resistor_heat_w"], delta=2e-12)
        self.assertGreater(max(abs(value(t["source_current_a"])-value(t["current_into_line_a"])) for t in point["terminals"]), 1e-4)
        for t in point["terminals"]:
            self.assertAlmostEqual(t["reactive_exchange_var"], 4*np.pi*1000*(t["inductor_average_energy_j"]-t["capacitor_average_energy_j"]), delta=2e-12)
        for t in raw["terminations"]: t.update(inductance_h=0., capacitance_f=0.)
        self.assertLess(loaded.run_rlgc_loaded_star(raw)["points"][0]["terminals"][0]["source_power_va"]["real"], 0)
        actual = loaded.run_rlgc_loaded_star(raw)["points"][0]
        expected = physical_oracle(raw, 0)
        np.testing.assert_allclose([value(t["current_into_line_a"]) for t in actual["terminals"]], expected[5], atol=2e-11, rtol=2e-9)
        original = loaded.pair.run_rlgc_coupled_pair
        mutated = False
        def corrupt_near_node(*args, **kwargs):
            nonlocal mutated
            child = original(*args, **kwargs)
            if args[0]["modes"]["even"]["length_m"] == .055:
                a = np.array([value(z) for z in args[0]["excitations"][0]["incident_waves"]])
                b = loaded.pair._decode(child["network"]["s_parameters"][0])@a
                scale = (np.linalg.norm(a[2:])+np.linalg.norm(b[2:]))/np.sqrt(50.)
                target = child["points"][0]["boundary_values"][2]["current_into_line_a"]
                target["real"] = float(target["real"]+1e-10*scale); mutated = True
            return child
        with patch.object(loaded.pair, "run_rlgc_coupled_pair", side_effect=corrupt_near_node):
            with self.assertRaisesRegex(loaded.LoadedStarError, "Child field differs") as caught:
                loaded.run_rlgc_loaded_star(raw)
        self.assertTrue(mutated); self.assertEqual(caught.exception.code, "LOADED_STAR_INVALID_RESULT")

    def test_eight_leg_physical_endpoint_upper_boundary(self):
        raw=request();model=raw["legs"][0];terminal=raw["terminations"][0]
        raw["legs"]=[{**deepcopy(model),"id":str(k)} for k in range(8)]
        raw["terminations"]=[{**deepcopy(terminal),"id":"t"+str(k),"port":k} for k in range(16)]
        for source in raw["sources"]:source["voltage_v"]=[{"real":.1*(k+1),"imag":-.01*k} for k in range(16)]
        out=loaded.run_rlgc_loaded_star(raw)
        expected=physical_oracle(raw,0)[4]
        np.testing.assert_allclose([value(t["voltage_v"]) for t in out["points"][0]["terminals"]],expected,atol=2e-11,rtol=2e-9)
        self.assertEqual(len(out["points"][0]["terminals"]),16)

    def test_admission_resources_condition_and_cancellation(self):
        mutations = [lambda r: r.__setitem__("extra", 1), lambda r: r.__setitem__("legs", []),
            lambda r: r["terminations"][0].__setitem__("inductance_h", -1), lambda r: r["terminations"][0].__setitem__("capacitance_f", True),
            lambda r: r["terminations"][0].__setitem__("resistance_ohm", 0),
            lambda r: r["terminations"][0].__setitem__("port", 1),
            lambda r: r["legs"][1]["pair"]["conductor_ids"].reverse(),
            lambda r: r["sources"][0].__setitem__("frequency_hz", 1),
            lambda r: [mode.__setitem__("reference_impedance_ohm", 75) for mode in r["legs"][1]["pair"]["modes"].values()],
            lambda r: r["sources"][0]["voltage_v"][0].__setitem__("real", float('inf'))]
        for mutate in mutations:
            raw = request(); mutate(raw)
            with patch.object(loaded, "_bare", side_effect=AssertionError("reject before numerical work")):
                with self.assertRaises(loaded.LoadedStarError): loaded.run_rlgc_loaded_star(raw)
        with patch.object(loaded, "_MAX_BYTES", 10):
            with self.assertRaisesRegex(loaded.LoadedStarError, "exceeds32MiB"): loaded.run_rlgc_loaded_star(request())
        with patch.object(loaded.cascade, "_MAX_WORK", 1):
            with self.assertRaisesRegex(loaded.LoadedStarError, "work exceeds"): loaded.run_rlgc_loaded_star(request())
        raw = request()
        for leg in raw["legs"]:
            for mode in leg["pair"]["modes"].values(): mode["samples"] = [{"frequency_hz": 1e-12, "resistance_ohm_per_m": 0., "conductance_s_per_m": 0.}]
        raw["sources"] = [deepcopy(raw["sources"][0])]; raw["sources"][0]["frequency_hz"] = 1e-12
        for t in raw["terminations"]: t.update(resistance_ohm=1e12, inductance_h=0., capacitance_f=0.)
        with self.assertRaisesRegex(loaded.LoadedStarError, "condition"): loaded.run_rlgc_loaded_star(raw)
        enormous = request(); enormous["sources"][0]["voltage_v"][0]["real"] = 1e308
        with self.assertRaises(loaded.LoadedStarError): loaded.run_rlgc_loaded_star(enormous)
        with self.assertRaisesRegex(loaded.LoadedStarError, "cancelled"): loaded.run_rlgc_loaded_star(request(), cancel_check=lambda: True)
        def fail(): raise RuntimeError("callback failed")
        with self.assertRaisesRegex(loaded.LoadedStarError, "callback failed"): loaded.run_rlgc_loaded_star(request(), cancel_check=fail)

    def test_child_provenance_network_field_ledger_forgery_and_late_cancellation(self):
        original = loaded.star.run_rlgc_coupled_star
        def swap_heat(child):
            heat = child["legs"][0]["result"]["points"][0]["power_balance"]
            heat["conductor_loss_w"], heat["dielectric_loss_w"] = heat["dielectric_loss_w"], heat["conductor_loss_w"]
        mutations = [lambda c: c.__setitem__("input_digest", "0"*64),
            lambda c: c["network"]["s_parameters"][0][0][0].__setitem__("real", 123),
            lambda c: c["legs"][0]["result"]["points"][0]["probe_values"][0]["conductors"][0]["voltage_v"].__setitem__("real", 999),
            swap_heat, lambda c: c["points"][0]["power_balance"].__setitem__("conductor_loss_w", 999),
            lambda c: c["points"][0]["junctions"][0].__setitem__("power_residual_w", 1),
            lambda c: c["legs"].reverse()]
        for mutate in mutations:
            def forged(*a, **kw):
                child = original(*a, **kw); mutate(child); return child
            with patch.object(loaded.star, "run_rlgc_coupled_star", side_effect=forged):
                with self.assertRaises(loaded.LoadedStarError): loaded.run_rlgc_loaded_star(request())
        cancelled = False
        def stop(*a, **kw):
            nonlocal cancelled
            child = original(*a, **kw); cancelled = True; return child
        with patch.object(loaded.star, "run_rlgc_coupled_star", side_effect=stop):
            with self.assertRaisesRegex(loaded.LoadedStarError, "cancelled"):
                loaded.run_rlgc_loaded_star(request(), cancel_check=lambda: cancelled)


if __name__ == "__main__":
    unittest.main()
