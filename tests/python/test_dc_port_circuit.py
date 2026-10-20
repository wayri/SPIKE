# SPDX-License-Identifier: Apache-2.0
"""Independent resistor-network checks for the reduced land-port circuit."""
from copy import deepcopy
import unittest

import numpy as np

from python.spike_core.dc_port_circuit import solve_port_circuit


def reduced_star(resistances):
    """Exact port response for resistors from every port to one ideal body."""
    r = np.asarray(resistances, dtype=float)
    return np.diag(r[:-1]) + r[-1] * np.ones((len(r) - 1, len(r) - 1))


def physical_mna(port_resistances, edges, sources):
    """Solve ordinary port/body-node MNA, independently of reduced responses."""
    counts = [len(row) for row in port_resistances]
    offsets = np.r_[0, np.cumsum(counts)]
    port_count = int(offsets[-1])
    body_nodes = np.arange(len(counts)) + port_count
    size = port_count + len(counts)
    conductance = np.zeros((size, size))

    def add_resistor(a, b, resistance):
        value = 1.0 / resistance
        conductance[a, a] += value
        conductance[b, b] += value
        conductance[a, b] -= value
        conductance[b, a] -= value

    for body, row in enumerate(port_resistances):
        for port, resistance in enumerate(row):
            add_resistor(int(offsets[body] + port), int(body_nodes[body]), resistance)
    for edge in edges:
        bp, pp = edge["p"]
        bn, pn = edge["n"]
        add_resistor(int(offsets[bp] + pp), int(offsets[bn] + pn), edge["resistance_ohm"])

    rhs = np.zeros(size)
    rhs[:port_count] = np.concatenate(sources)
    keep = np.arange(size) != body_nodes[0]
    voltage = np.zeros(size)
    voltage[keep] = np.linalg.solve(conductance[np.ix_(keep, keep)], rhs[keep])
    edge_current = np.asarray([
        (voltage[int(offsets[e["p"][0]] + e["p"][1])]
         - voltage[int(offsets[e["n"][0]] + e["n"][1])]) / e["resistance_ohm"]
        for e in edges
    ])
    body_current = [
        (voltage[offsets[b]:offsets[b + 1]] - voltage[body_nodes[b]])
        / np.asarray(port_resistances[b])
        for b in range(len(counts))
    ]
    body_heat = [float(np.dot(i * i, r)) for i, r in zip(body_current, port_resistances)]
    edge_heat = np.asarray([e["resistance_ohm"] for e in edges]) * edge_current**2
    work = float(np.concatenate(sources) @ voltage[:port_count])
    return {
        "edge_current": edge_current,
        "port_voltage": [voltage[offsets[b]:offsets[b + 1]] for b in range(len(counts))],
        "body_current": body_current,
        "body_heat": np.asarray(body_heat),
        "edge_heat": edge_heat,
        "work": work,
    }


def fixture():
    resistances = [[1.5, 2.0, 3.0], [2.5, 1.0], [4.0, 2.0, 5.0]]
    edges = [
        {"p": [0, 0], "n": [1, 0], "resistance_ohm": 4.0},
        {"p": [0, 1], "n": [1, 1], "resistance_ohm": 7.0},
        {"p": [1, 0], "n": [2, 0], "resistance_ohm": 5.0},
        {"p": [2, 1], "n": [0, 2], "resistance_ohm": 9.0},
        # A real loop through two distinct ports on the same physical land.
        {"p": [2, 2], "n": [2, 1], "resistance_ohm": 11.0},
    ]
    sources = [np.array([1.2, -0.1, 0.3]), np.array([-0.4, 0.2]),
               np.array([-0.5, -0.3, -0.4])]
    return resistances, edges, sources


class PortCircuitTests(unittest.TestCase):
    def test_independent_physical_mna_parallel_and_intrabody(self):
        resistances, edges, sources = fixture()
        expected = physical_mna(resistances, edges, sources)
        actual = solve_port_circuit([reduced_star(r) for r in resistances], edges, sources)
        np.testing.assert_allclose(actual["edge_current_a"], expected["edge_current"], atol=2e-12, rtol=2e-10)
        np.testing.assert_allclose(actual["edge_heat_w"], expected["edge_heat"], atol=2e-12, rtol=2e-10)
        np.testing.assert_allclose(actual["body_heat_w"], expected["body_heat"], atol=2e-12, rtol=2e-10)
        np.testing.assert_allclose(actual["source_work_w"], expected["work"], atol=2e-12, rtol=2e-10)
        np.testing.assert_allclose(actual["total_heat_w"], expected["work"], atol=2e-12, rtol=2e-10)
        for got_i, want_i, got_u, want_u in zip(actual["body_currents_a"], expected["body_current"],
                                                actual["body_port_potentials_v"], expected["port_voltage"]):
            np.testing.assert_allclose(got_i, want_i, atol=2e-12, rtol=2e-10)
            # The global voltage gauge may differ, so compare all port differences.
            np.testing.assert_allclose(np.subtract.outer(got_u, got_u), np.subtract.outer(want_u, want_u),
                                       atol=2e-12, rtol=2e-10)
        self.assertLess(actual["diagnostics"]["maximum_body_kcl_a"], 2e-12)
        self.assertLess(actual["diagnostics"]["maximum_edge_kvl_v"], 2e-12)

    def test_body_port_reference_and_record_order_invariance(self):
        resistances, edges, sources = fixture()
        baseline = solve_port_circuit([reduced_star(r) for r in resistances], edges, sources)
        port_orders = [[2, 0, 1], [1, 0], [1, 2, 0]]
        inverse = [{old: new for new, old in enumerate(order)} for order in port_orders]
        changed_r = [[row[i] for i in order] for row, order in zip(resistances, port_orders)]
        changed_s = [row[order] for row, order in zip(sources, port_orders)]
        changed_edges = [{**edge,
            "p": [edge["p"][0], inverse[edge["p"][0]][edge["p"][1]]],
            "n": [edge["n"][0], inverse[edge["n"][0]][edge["n"][1]]]} for edge in edges]
        changed = solve_port_circuit([reduced_star(r) for r in changed_r], changed_edges, changed_s)
        np.testing.assert_allclose(changed["edge_current_a"], baseline["edge_current_a"], atol=2e-12, rtol=2e-10)
        np.testing.assert_allclose(changed["body_heat_w"], baseline["body_heat_w"], atol=2e-12, rtol=2e-10)
        self.assertAlmostEqual(changed["source_work_w"], baseline["source_work_w"], delta=2e-12)

        body_order = [2, 0, 1]
        body_inverse = {old: new for new, old in enumerate(body_order)}
        reordered_edges = [{**edge,
            "p": [body_inverse[edge["p"][0]], edge["p"][1]],
            "n": [body_inverse[edge["n"][0]], edge["n"][1]]} for edge in edges]
        reordered = solve_port_circuit([reduced_star(resistances[i]) for i in body_order],
                                       reordered_edges, [sources[i] for i in body_order])
        np.testing.assert_allclose(reordered["edge_current_a"], baseline["edge_current_a"], atol=2e-12, rtol=2e-10)
        np.testing.assert_allclose(np.asarray(reordered["body_heat_w"])[[body_inverse[i] for i in range(3)]],
                                   baseline["body_heat_w"], atol=2e-12, rtol=2e-10)
        self.assertAlmostEqual(reordered["source_work_w"], baseline["source_work_w"], delta=2e-12)

    def test_zero_scaling_and_edge_orientation(self):
        resistances, edges, sources = fixture()
        baseline = solve_port_circuit([reduced_star(r) for r in resistances], edges, sources)
        zero = solve_port_circuit([reduced_star(r) for r in resistances], edges,
                                  [np.zeros_like(row) for row in sources])
        self.assertEqual(zero["source_work_w"], 0.0)
        self.assertEqual(zero["total_heat_w"], 0.0)
        np.testing.assert_array_equal(zero["edge_current_a"], 0.0)
        for factor in (-2.0, 0.25):
            actual = solve_port_circuit([reduced_star(r) for r in resistances], edges,
                                        [factor * row for row in sources])
            np.testing.assert_allclose(actual["edge_current_a"], factor * np.asarray(baseline["edge_current_a"]),
                                       atol=2e-12, rtol=2e-10)
            self.assertAlmostEqual(actual["total_heat_w"], factor**2 * baseline["total_heat_w"], delta=2e-12)
        reversed_edges = deepcopy(edges)
        for edge in reversed_edges:
            edge["p"], edge["n"] = edge["n"], edge["p"]
        reversed_result = solve_port_circuit([reduced_star(r) for r in resistances], reversed_edges, sources)
        np.testing.assert_allclose(reversed_result["edge_current_a"], -np.asarray(baseline["edge_current_a"]),
                                   atol=2e-12, rtol=2e-10)
        np.testing.assert_allclose(reversed_result["edge_heat_w"], baseline["edge_heat_w"], atol=2e-12, rtol=2e-10)

    def test_simple_barrel_and_admission_fail_closed(self):
        simple = solve_port_circuit([np.empty((0, 0)), np.empty((0, 0))],
                                    [{"p": [0, 0], "n": [1, 0], "resistance_ohm": 3.0}],
                                    [np.array([2.0]), np.array([-2.0])])
        self.assertAlmostEqual(simple["edge_current_a"][0], 2.0)
        self.assertAlmostEqual(simple["source_work_w"], 12.0)
        self.assertEqual(simple["body_heat_w"], [0.0, 0.0])

        valid_r, valid_e, valid_s = fixture()
        cases = []
        disconnected = deepcopy(valid_e)
        disconnected[:] = [e for e in disconnected if e["p"][0] != 2 and e["n"][0] != 2]
        cases.append(([reduced_star(r) for r in valid_r], disconnected, valid_s))
        unbalanced = [row.copy() for row in valid_s]; unbalanced[0][0] += 0.1
        cases.append(([reduced_star(r) for r in valid_r], valid_e, unbalanced))
        bad_edge = deepcopy(valid_e); bad_edge[0]["resistance_ohm"] = 0.0
        cases.append(([reduced_star(r) for r in valid_r], bad_edge, valid_s))
        indefinite = [reduced_star(r) for r in valid_r]; indefinite[0] = np.array([[1., 2.], [2., 1.]])
        cases.append((indefinite, valid_e, valid_s))
        nonreciprocal = [reduced_star(r) for r in valid_r]; nonreciprocal[0] = np.array([[2., 1.], [0., 2.]])
        cases.append((nonreciprocal, valid_e, valid_s))
        for responses, edges, sources in cases:
            with self.assertRaises(ValueError):
                solve_port_circuit(responses, edges, sources)

        ill_edges = [
            {"p": [0, 0], "n": [1, 0], "resistance_ohm": 1e-12},
            {"p": [1, 0], "n": [2, 0], "resistance_ohm": 1.0},
            {"p": [2, 0], "n": [3, 0], "resistance_ohm": 1e12},
        ]
        with self.assertRaisesRegex(ValueError, "condition"):
            solve_port_circuit([np.empty((0, 0))] * 4, ill_edges,
                               [np.array([1.]), np.array([0.]), np.array([0.]), np.array([-1.])])


if __name__ == "__main__":
    unittest.main()
