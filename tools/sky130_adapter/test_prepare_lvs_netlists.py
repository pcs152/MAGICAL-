#!/usr/bin/env python3
"""Tests for LVS netlist preparation."""

from __future__ import annotations

import unittest

from prepare_lvs_netlists import source_to_connectivity


class PrepareLvsNetlistsTest(unittest.TestCase):
    def test_source_capacitor_pins_are_flattened_for_netgen(self) -> None:
        source = [
            ".subckt top net050 vout\n",
            "C0 (net050 vout) cfmom_2t nr=15 lr=30u w=70n\n",
            ".ends top\n",
        ]

        output, saw_subckt, saw_ends = source_to_connectivity(source)

        self.assertTrue(saw_subckt)
        self.assertTrue(saw_ends)
        self.assertIn("C0 net050 vout cfmom_2t nr=15 lr=30u w=70n\n", output)
        self.assertNotIn("vout)", "".join(output))
        self.assertNotIn("(net050", "".join(output))


if __name__ == "__main__":
    unittest.main()
