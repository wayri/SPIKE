# SPDX-License-Identifier: Apache-2.0
"""Operation-order and full-candidate oracles for predicate allocation changes."""
from fractions import Fraction
import itertools
import random
import unittest
from unittest.mock import patch

from python.spike_core import internal_tetra_generation as generation


def reference_det3(rows):
    a, b, c = rows
    return (a[0]*(b[1]*c[2]-b[2]*c[1]) -
            a[1]*(b[0]*c[2]-b[2]*c[0]) +
            a[2]*(b[0]*c[1]-b[1]*c[0]))


def reference_det4(rows):
    # Retain the original cofactor operation order, including Python's sum.
    return sum((-1 if j % 2 else 1) * rows[0][j] *
               reference_det3([[row[k] for k in range(4) if k != j]
                               for row in rows[1:]]) for j in range(4))


def permutation_determinant(rows):
    total = Fraction(0)
    for order in itertools.permutations(range(4)):
        inversions = sum(order[i] > order[j] for i in range(4) for j in range(i+1, 4))
        term = Fraction((-1)**inversions)
        for i, j in enumerate(order):
            term *= rows[i][j]
        total += term
    return total


def reference_sphere_determinant(points, cell, point):
    origin = points[point]
    rows = [[points[i][k]-origin[k] for k in range(3)] for i in cell]
    return generation._det4([row + [sum(x*x for x in row)] for row in rows])


class PredicateAllocationTests(unittest.TestCase):
    def test_sphere_lift_preserves_float_bits_and_exact_values(self):
        rng = random.Random(101212)
        for _ in range(200):
            points = [[rng.uniform(-1, 1)*2**rng.randrange(-80, 80)
                       for _ in range(3)] for _ in range(5)]
            self.assertEqual(generation._sphere_determinant(points, (0, 1, 2, 3), 4).hex(),
                             reference_sphere_determinant(points, (0, 1, 2, 3), 4).hex())
            exact = [list(map(Fraction, point)) for point in points]
            self.assertEqual(generation._sphere_determinant(exact, (0, 1, 2, 3), 4),
                             reference_sphere_determinant(exact, (0, 1, 2, 3), 4))

    def test_float_operation_order_is_bit_exact(self):
        rng = random.Random(81012)
        matrices = [[[rng.uniform(-1, 1)*2**rng.randrange(-100, 100)
                      for _ in range(4)] for _ in range(4)] for _ in range(300)]
        matrices += [[[0.0]*4 for _ in range(4)],
                     [[float(i == j) for j in range(4)] for i in range(4)]]
        for rows in matrices:
            self.assertEqual(generation._det4(rows).hex(), reference_det4(rows).hex())

    def test_exact_cofactors_match_independent_permutation_oracle(self):
        rng = random.Random(4031)
        for _ in range(30):
            rows = [[Fraction(rng.randrange(-12, 13), 2**rng.randrange(8))
                     for _ in range(4)] for _ in range(4)]
            self.assertEqual(generation._det4(rows), permutation_determinant(rows))

    def test_complete_candidate_and_predicate_evidence_are_unchanged(self):
        rng = random.Random(7201)
        clouds = [[list(point) for point in itertools.product((0, 1), repeat=3)],
                  [list(point) for point in itertools.product((0, .5, 1), repeat=3)],
                  [[rng.random() for _ in range(3)] for _ in range(40)]]
        for points in clouds:
            expected = generation.generate_tetra_mesh(points)
            with patch.object(generation, '_det4', reference_det4):
                with patch.object(generation, '_sphere_determinant', reference_sphere_determinant):
                    reference = generation.generate_tetra_mesh(points)
            self.assertEqual(expected, reference)

    def test_existing_finite_enclosure_rejection_is_unchanged(self):
        rng = random.Random(7201)
        points = [[rng.random() for _ in range(3)] for _ in range(32)]
        with self.assertRaises(generation.TetraGenerationError) as optimized:
            generation.generate_tetra_mesh(points)
        with patch.object(generation, '_det4', reference_det4):
            with patch.object(generation, '_sphere_determinant', reference_sphere_determinant):
                with self.assertRaises(generation.TetraGenerationError) as reference:
                    generation.generate_tetra_mesh(points)
        self.assertEqual(str(optimized.exception), str(reference.exception))
        self.assertIn('supporting convex hull', str(optimized.exception))


if __name__ == '__main__':
    unittest.main()
