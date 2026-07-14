from __future__ import annotations

import unittest

from taekbae.nodelink import _shortest_path


class NodeLinkTests(unittest.TestCase):
    def test_shortest_path_uses_directed_link_lengths(self) -> None:
        adjacency = {
            "a": [(5.0, "b", {"link_id": "ab"}), (20.0, "c", {"link_id": "ac"})],
            "b": [(4.0, "c", {"link_id": "bc"})],
            "c": [],
        }
        result = _shortest_path(adjacency, "a", "c")
        self.assertIsNotNone(result)
        distance, links = result or (0, [])
        self.assertEqual(9.0, distance)
        self.assertEqual(["ab", "bc"], [link["link_id"] for link in links])
        self.assertIsNone(_shortest_path(adjacency, "c", "a"))
