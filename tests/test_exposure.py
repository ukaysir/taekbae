from __future__ import annotations

import unittest

from taekbae.exposure import _distance_squared, _point_segment_distance_squared


class ExposureGeometryTests(unittest.TestCase):
    def test_point_to_segment_distance_uses_nearest_projection(self) -> None:
        distance = _point_segment_distance_squared((5.0, 3.0), (0.0, 0.0), (10.0, 0.0))
        self.assertEqual(9.0, distance)

    def test_point_geometry_distance_is_euclidean(self) -> None:
        distance = _distance_squared(
            (4.0, 6.0), geometry_type="node", parts=[[(1.0, 2.0)]]
        )
        self.assertEqual(25.0, distance)

    def test_polyline_distance_checks_every_segment(self) -> None:
        distance = _distance_squared(
            (8.0, 2.0),
            geometry_type="link_path",
            parts=[[(0.0, 0.0), (5.0, 0.0), (5.0, 5.0)]],
        )
        self.assertEqual(9.0, distance)
