# SPDX-License-Identifier: Apache-2.0
"""Identical pad polygons reuse work without reusing mutable admission state."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from python.spike_core import custom_pad_geometry as geometry


def pad(points=None):
    return SimpleNamespace(shape="custom", drill_size_mm=(0., 0.), custom_geometry={
        "status": "supported", "coordinate_space": "pad_local_mm", "mirror_x": False,
        "positive_filled_polygon": deepcopy(points or [[0., 0.], [2., 0.], [2., 1.], [0., 1.]]),
    })


class CustomPadValidationReuseTests(unittest.TestCase):
    def test_repeated_geometry_keeps_every_pad_metadata_check(self):
        first, second = pad(), pad()
        with patch.object(geometry, "_polygon_is_simple", wraps=geometry._polygon_is_simple) as predicate:
            geometry.validate_custom_pad_geometries([first, second])
            self.assertEqual(predicate.call_count, 1)
        second.custom_geometry["mirror_x"] = "false"
        with self.assertRaisesRegex(ValueError, "coordinate space"):
            geometry.validate_custom_pad_geometries([first, second])

    def test_mutation_and_new_calls_never_reuse_old_acceptance(self):
        first = pad()
        geometry.validate_custom_pad_geometries([first])
        first.custom_geometry["positive_filled_polygon"][2] = [float("nan"), 1.]
        with self.assertRaisesRegex(ValueError, "coordinates"):
            geometry.validate_custom_pad_geometries([first])
        first = pad()
        second = pad([[0., 0.], [2., 1.], [0., 1.], [2., 0.]])
        with self.assertRaisesRegex(ValueError, "simple"):
            geometry.validate_custom_pad_geometries([first, second])

    def test_unique_geometry_does_not_displace_required_validation(self):
        pads = [pad([[float(i), 0.], [i + 2., 0.], [i + 2., 1.], [float(i), 1.]])
                for i in range(129)]
        with patch.object(geometry, "_polygon_is_simple", wraps=geometry._polygon_is_simple) as predicate:
            geometry.validate_custom_pad_geometries([*pads, pad()])
            self.assertEqual(predicate.call_count, 129)


if __name__ == "__main__":
    unittest.main()
