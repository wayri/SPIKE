# SPDX-License-Identifier: Apache-2.0
"""Original SI08-I01 physical V/I oracles; no external fixtures or kernels."""
from copy import deepcopy
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core.solvers.signal_integrity.networks.sparameters import NetworkData
from python.spike_core.solvers.signal_integrity.networks.sparameter_modes import mixed_mode_network


ATOL = 3e-14
RTOL = 3e-13


def partition(count):
    """Outside-in, nonadjacent pairs; odd counts retain the middle port."""
    pairs = [(i, count - 1 - i) for i in range(count // 2)]
    return pairs, [count // 2] if count % 2 else []


def references(count, pairs):
    refs = np.full(count, 37.0)
    for index, (positive, negative) in enumerate(pairs):
        refs[[positive, negative]] = 23.0 + 7.0 * index
    return refs


def dense_samples(count):
    """Deterministic asymmetric complex data; frequency grid includes supplied DC."""
    row, col = np.indices((count, count))
    base = ((1 + (3 * row + 5 * col) % 19)
            + 1j * (2 + (7 * row + 2 * col) % 23)) / (60 * count)
    return np.array([base, (0.7 - 0.2j) * base + 0.05j * np.eye(count)])


def make_network(samples, refs, kind="S"):
    return NetworkData(np.array([0.0, 2.75e9])[:len(samples)], samples,
                       np.array(refs), kind, "RI", "original-si08-i01-synthetic",
                       ["Supplied samples, including DC."], ["No causality qualification."])


def modal_vi(voltage, current, pairs, singles):
    """Physical definitions, deliberately without a wave transform matrix."""
    vm, im = [], []
    for positive, negative in pairs:
        vm.append(voltage[positive] - voltage[negative])
        im.append((current[positive] - current[negative]) / 2)
    for positive, negative in pairs:
        vm.append((voltage[positive] + voltage[negative]) / 2)
        im.append(current[positive] + current[negative])
    for port in singles:
        vm.append(voltage[port])
        im.append(current[port])
    return np.array(vm), np.array(im)


def physical_oracle(samples, refs, pairs, singles):
    """Excite each modal source in V/A, then measure outgoing modal waves."""
    count, pair_count = len(refs), len(pairs)
    mode_refs = np.array([2 * refs[p] for p, _ in pairs]
                         + [refs[p] / 2 for p, _ in pairs]
                         + [refs[p] for p in singles])
    # Unit incident wave at each mode with no outgoing incident component.
    vm = np.diag(np.sqrt(mode_refs))
    im = np.diag(1 / np.sqrt(mode_refs))
    voltage, current = np.zeros((count, count)), np.zeros((count, count))
    for index, (positive, negative) in enumerate(pairs):
        voltage[positive] = vm[pair_count + index] + vm[index] / 2
        voltage[negative] = vm[pair_count + index] - vm[index] / 2
        current[positive] = im[index] + im[pair_count + index] / 2
        current[negative] = -im[index] + im[pair_count + index] / 2
    for index, port in enumerate(singles, 2 * pair_count):
        voltage[port], current[port] = vm[index], im[index]
    root = np.sqrt(refs)[:, None]
    incident = (voltage + refs[:, None] * current) / (2 * root)
    answers, powers = [], []
    for sample in samples:
        outgoing = sample @ incident
        voltage = root * (incident + outgoing)
        current = (incident - outgoing) / root
        vm, im = modal_vi(voltage, current, pairs, singles)
        a = (vm + mode_refs[:, None] * im) / (2 * np.sqrt(mode_refs)[:, None])
        b = (vm - mode_refs[:, None] * im) / (2 * np.sqrt(mode_refs)[:, None])
        np.testing.assert_allclose(a, np.eye(count), atol=ATOL, rtol=RTOL)
        physical_power = np.sum(np.real(voltage * current.conj()), axis=0)
        modal_power = np.sum(np.abs(a)**2 - np.abs(b)**2, axis=0)
        np.testing.assert_allclose(modal_power, physical_power, atol=ATOL, rtol=RTOL)
        answers.append(b)
        powers.append(physical_power)
    return np.array(answers), mode_refs, np.array(powers)


class InteroperabilityOracleTests(unittest.TestCase):
    def assert_close(self, actual, expected):
        np.testing.assert_allclose(actual, expected, atol=ATOL, rtol=RTOL)

    def test_every_port_count_two_through_sixty_four_physical_oracle(self):
        for count in range(2, 65):
            with self.subTest(ports=count):
                pairs, singles = partition(count)
                refs = references(count, pairs)
                source = make_network(dense_samples(count), refs)
                expected, mode_refs, power = physical_oracle(source.parameters, refs, pairs, singles)
                result = mixed_mode_network(source, pairs, singles)
                self.assert_close(result.network.parameters, expected)
                np.testing.assert_array_equal(result.network.reference_impedance_ohm, mode_refs)
                self.assert_close(1 - np.sum(abs(result.network.parameters)**2, axis=1), power)
                for index, (positive, negative) in enumerate(pairs):
                    for offset, kind in ((0, "differential"), (len(pairs), "common")):
                        self.assertEqual(result.port_mapping[offset + index], {
                            "kind": kind, "pair_index": index, "positive_port": positive,
                            "negative_port": negative, "positive_name": f"P{positive + 1}",
                            "negative_name": f"P{negative + 1}"})
                for offset, port in enumerate(singles, 2 * len(pairs)):
                    self.assertEqual(result.port_mapping[offset], {
                        "kind": "single_ended", "port": port, "name": f"P{port + 1}"})

    def test_receiver_source_asymmetry_and_polarity_closed_form(self):
        samples = np.zeros((1, 5, 5), complex)
        samples[0, 4, 1], samples[0, 1, 4] = 0.6 + 0.2j, -0.1 + 0.3j
        result = mixed_mode_network(make_network(samples, [50]*5), [(1, 3), (4, 0)], [2])
        self.assert_close(result.network.parameters[0, 1, 0], 0.3 + 0.1j)
        self.assert_close(result.network.parameters[0, 0, 1], -0.05 + 0.15j)
        reversed_result = mixed_mode_network(make_network(samples, [50]*5), [(3, 1), (4, 0)], [2])
        signs = np.array([-1, 1, 1, 1, 1])
        self.assert_close(reversed_result.network.parameters,
                          result.network.parameters * signs[:, None] * signs[None, :])

    def test_physical_permutation_pair_order_and_single_order(self):
        pairs, singles = [(6, 1), (0, 4)], [5, 2, 3]
        refs = references(7, pairs)
        source = make_network(dense_samples(7), refs)
        names = [f"physical-terminal-{i}" for i in range(7)]
        original = mixed_mode_network(source, pairs, singles, port_names=names)
        permutation = np.array([3, 6, 2, 0, 5, 4, 1])
        inverse = np.argsort(permutation)
        moved = make_network(source.parameters[:, permutation][:, :, permutation], refs[permutation])
        result = mixed_mode_network(moved, [(int(inverse[p]), int(inverse[n])) for p, n in pairs],
                                    [int(inverse[p]) for p in singles],
                                    port_names=[names[p] for p in permutation])
        self.assert_close(result.network.parameters, original.network.parameters)
        self.assert_close(result.network.reference_impedance_ohm, original.network.reference_impedance_ohm)
        for before, after in zip(original.port_mapping, result.port_mapping):
            for key in ("kind", "positive_name", "negative_name", "name"):
                if key in before:
                    self.assertEqual(before[key], after[key])
        reordered = mixed_mode_network(source, pairs[::-1], singles[::-1], port_names=names)
        order = [1, 0, 3, 2, 6, 5, 4]
        self.assert_close(reordered.network.parameters, original.network.parameters[:, order][:, :, order])
        self.assert_close(reordered.network.reference_impedance_ohm, original.network.reference_impedance_ohm[order])

    def test_z_y_inputs_against_physical_boundary_current_solve(self):
        for count in (2, 3, 7, 16, 64):
            pairs, singles = partition(count)
            refs = references(count, pairs)
            row, col = np.indices((count, count))
            z = np.diag(refs * 1.3) + (row + 2 * col + 1j * (2 * row - col)) / (8 * count)
            root = np.sqrt(refs)[:, None]
            # V=ZI and V+RI=2 sqrt(R) a; columns each apply a unit source.
            self.assertLess(np.linalg.cond(z + np.diag(refs)), 25)
            current = np.linalg.solve(z + np.diag(refs), 2 * np.diag(np.sqrt(refs)))
            voltage = z @ current
            s = ((voltage - refs[:, None] * current) / (2 * root))[None]
            expected, _, _ = physical_oracle(s, refs, pairs, singles)
            for kind, sample in (("S", s[0]), ("Z", z), ("Y", np.linalg.solve(z, np.eye(count)))):
                with self.subTest(ports=count, representation=kind):
                    result = mixed_mode_network(make_network(sample[None], refs, kind), pairs, singles)
                    self.assert_close(result.network.parameters, expected)

    def test_source_ownership_and_warning_preservation(self):
        pairs, singles = partition(7)
        source = make_network(dense_samples(7), references(7, pairs))
        saved = deepcopy(source)
        names = [f"terminal-{i}" for i in range(7)]
        result = mixed_mode_network(source, pairs, singles, port_names=names)
        self.assertEqual(result.network.source, source.source)
        self.assertEqual(result.network.warnings, saved.warnings)
        self.assertEqual(result.network.comments[:-1], saved.comments)
        for field in ("parameters", "frequencies_hz", "reference_impedance_ohm"):
            self.assertFalse(np.shares_memory(getattr(source, field), getattr(result.network, field)))
            getattr(result.network, field).flat[0] = 123
            np.testing.assert_array_equal(getattr(source, field), getattr(saved, field))
        result.network.comments.append("derived mutation")
        result.network.warnings.append("derived warning")
        result.port_mapping[0]["positive_name"] = "derived mapping mutation"
        self.assertEqual(source.comments, saved.comments)
        self.assertEqual(source.warnings, saved.warnings)
        self.assertEqual(names[0], "terminal-0")
        self.assertEqual(source.parameter_kind, saved.parameter_kind)
        self.assertEqual(source.data_format, saved.data_format)

    def test_invalid_partition_and_names_rejected_before_conversion(self):
        cases = [([], [0, 1, 2, 3]), ([(0, 1)], []), ([(0, 1), (1, 3)], []),
                 ([(0, 0)], [2, 3]), ([(0, -1)], [1, 2]), ([(0, 4)], [1, 2]),
                 ([(True, 0)], [2, 3]), ([(np.bool_(True), 0)], [2, 3]),
                 ([(0.0, 1)], [2, 3]), ([(0,)], [1, 2, 3]),
                 ([(0, 1, 2)], [3]), ([(0, 1)], [2, 2])]
        source = make_network(dense_samples(4), [50]*4)
        for pairs, singles in cases:
            with self.subTest(pairs=pairs, singles=singles), patch.object(source, "s_parameters") as conversion:
                with self.assertRaises(ValueError):
                    mixed_mode_network(source, pairs, singles)
                conversion.assert_not_called()
        for names in (["same"]*4, ["a", "b", "c"], ["a", "b", "c", " "], ["a", "b", "c", 4]):
            with self.subTest(names=names), self.assertRaises(ValueError):
                mixed_mode_network(source, [(0, 1), (2, 3)], port_names=names)

    def test_invalid_data_and_within_pair_references(self):
        for field, values in (
            ("reference_impedance_ohm", [50, 51]), ("reference_impedance_ohm", [50+0j, 50+0j]),
            ("reference_impedance_ohm", [True, True]), ("reference_impedance_ohm", [0, 0]),
            ("reference_impedance_ohm", [-50, -50]), ("reference_impedance_ohm", [np.inf, np.inf]),
            ("reference_impedance_ohm", [np.nan, np.nan]), ("reference_impedance_ohm", [[50, 50]]),
            ("frequencies_hz", [-1, 1]), ("frequencies_hz", [0, 0]),
            ("frequencies_hz", [1, 0]), ("frequencies_hz", [0, np.nan]),
            ("frequencies_hz", [0, np.inf]), ("frequencies_hz", [0+0j, 1+0j]),
            ("parameters", np.full((2, 2, 2), np.nan)), ("parameters", np.full((2, 2, 2), np.inf)),
        ):
            with self.subTest(field=field, values=values):
                source = make_network(dense_samples(2), [50, 50])
                setattr(source, field, np.asarray(values))
                with self.assertRaises(ValueError):
                    mixed_mode_network(source, [(0, 1)])

    def test_sample_cap_executes_and_excess_rejects(self):
        count = 32769
        samples = np.broadcast_to(np.array([[0.2, 0.1j], [0.3, -0.2]]), (count, 2, 2))
        source = NetworkData(np.arange(count, dtype=float), samples, np.array([50., 50.]))
        result = mixed_mode_network(source, [(0, 1)]).network
        expected, _, _ = physical_oracle(samples[:1], source.reference_impedance_ohm, [(0, 1)], [])
        self.assertEqual(result.parameters.shape, (32769, 2, 2))
        self.assert_close(result.parameters[0], expected[0])
        self.assert_close(result.parameters[-1], expected[0])
        source.parameters = np.broadcast_to(samples[0], (32770, 2, 2))
        with patch.object(source, "s_parameters") as conversion, self.assertRaises(ValueError):
            mixed_mode_network(source, [(0, 1)])
        conversion.assert_not_called()

    def test_entry_cap_admission_without_large_allocation(self):
        class ReachedConversion(Exception):
            pass
        pairs, singles = partition(64)
        for sample_count, accepted in ((1024, True), (1025, False)):
            # Broadcast views consume one scalar; stop before any dense conversion.
            raw = np.broadcast_to(np.array(0j), (sample_count, 64, 64))
            source = NetworkData(np.arange(sample_count, dtype=float), raw, np.full(64, 50.))
            with self.subTest(entries=raw.size), patch.object(source, "s_parameters", side_effect=ReachedConversion) as conversion:
                with self.assertRaises(ReachedConversion if accepted else ValueError):
                    mixed_mode_network(source, pairs, singles)
                self.assertEqual(conversion.call_count, int(accepted))

    def test_invalid_shapes_and_port_cap_reject_before_conversion(self):
        for shape in ((1, 65, 65), (0, 2, 2), (1, 0, 0), (1, 2, 3), (2, 2), (2,)):
            source = make_network(np.broadcast_to(np.array(0j), shape), [50, 50])
            with self.subTest(shape=shape), patch.object(source, "s_parameters") as conversion:
                with self.assertRaises(ValueError):
                    mixed_mode_network(source, [(0, 1)])
                conversion.assert_not_called()


if __name__ == "__main__":
    unittest.main()
