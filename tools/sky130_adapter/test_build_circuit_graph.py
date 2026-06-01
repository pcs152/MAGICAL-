#!/usr/bin/env python3
"""Tests for MAGICAL netlist to circuit-graph conversion."""

from __future__ import annotations

import unittest

from build_circuit_graph import build_graph_from_text


class BuildCircuitGraphTest(unittest.TestCase):
    def test_inverter_graph_has_mos_ports_and_pin_edges(self) -> None:
        graph = build_graph_from_text(
            """
            subckt inverter_core A Y VPWR VGND
            M0 (Y A VGND VGND) sky130_fd_pr__nfet_01v8 l=150n w=1u multi=1 nf=1
            M1 (Y A VPWR VPWR) sky130_fd_pr__pfet_01v8 l=150n w=2u multi=1 nf=1
            ends inverter_core
            """,
            top_cell="inverter_core",
        )

        device_nodes = [node for node in graph["nodes"] if node["node_type"] == "device"]
        net_nodes = {node["id"]: node for node in graph["nodes"] if node["node_type"] == "net"}

        self.assertEqual(graph["schema_version"], "circuit_graph.v1")
        self.assertEqual(graph["top_cell"], "inverter_core")
        self.assertEqual(len(device_nodes), 2)
        self.assertEqual(set(graph["ports"]), {"A", "Y", "VPWR", "VGND"})
        self.assertEqual(net_nodes["Y"]["role"], "output")
        self.assertEqual(net_nodes["VPWR"]["role"], "power")
        self.assertEqual(net_nodes["VGND"]["role"], "ground")
        self.assertEqual(len(graph["edges"]), 8)
        self.assertIn({"source": "M0", "target": "Y", "pin": "D", "edge_type": "device_net_connection"}, graph["edges"])
        self.assertIn({"source": "M0", "target": "A", "pin": "G", "edge_type": "device_net_connection"}, graph["edges"])

    def test_ota_graph_assigns_differential_and_bias_roles(self) -> None:
        graph = build_graph_from_text(
            """
            subckt ota_core VINP VINM IB VDD VOUT GND
            M6 (net1 VINP net2 GND) sky130_fd_pr__nfet_01v8 l=150n w=1.26u multi=1 nf=2
            M7 (VOUT net1 VDD VDD) sky130_fd_pr__pfet_01v8 l=150n w=1.26u multi=1 nf=2
            M8 (net1 net1 VDD VDD) sky130_fd_pr__pfet_01v8 l=150n w=1.26u multi=1 nf=2
            M2 (VOUT VINM net2 GND) sky130_fd_pr__nfet_01v8 l=150n w=1.26u multi=1 nf=2
            M1 (net2 IB GND GND) sky130_fd_pr__nfet_01v8 l=150n w=1.26u multi=1 nf=2
            ends ota_core
            """,
            top_cell="ota_core",
        )

        device_nodes = [node for node in graph["nodes"] if node["node_type"] == "device"]
        net_nodes = {node["id"]: node for node in graph["nodes"] if node["node_type"] == "net"}

        self.assertEqual(len(device_nodes), 5)
        self.assertEqual(set(graph["ports"]), {"VINP", "VINM", "IB", "VDD", "VOUT", "GND"})
        self.assertEqual(net_nodes["VINP"]["role"], "differential_input_plus")
        self.assertEqual(net_nodes["VINM"]["role"], "differential_input_minus")
        self.assertEqual(net_nodes["IB"]["role"], "bias")
        self.assertEqual(net_nodes["VOUT"]["role"], "output")
        self.assertEqual(net_nodes["net1"]["role"], "internal")
        self.assertEqual(len(graph["edges"]), 20)


if __name__ == "__main__":
    unittest.main()
