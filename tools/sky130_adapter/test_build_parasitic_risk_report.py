#!/usr/bin/env python3
"""Tests for V1 parasitic risk report generation."""

from __future__ import annotations

import unittest

from build_parasitic_risk_report import build_risk_report


class BuildParasiticRiskReportTest(unittest.TestCase):
    def test_ota_roles_and_pex_caps_become_explainable_findings(self) -> None:
        graph = {
            "schema_version": "circuit_graph.v1",
            "top_cell": "ota_core",
            "ports": ["VINP", "VINM", "IB", "VDD", "VOUT", "GND"],
            "nodes": [
                {"id": "VINP", "node_type": "net", "role": "differential_input_plus", "is_port": True, "degree": 1},
                {"id": "VINM", "node_type": "net", "role": "differential_input_minus", "is_port": True, "degree": 1},
                {"id": "IB", "node_type": "net", "role": "bias", "is_port": True, "degree": 1},
                {"id": "VDD", "node_type": "net", "role": "power", "is_port": True, "degree": 4},
                {"id": "VOUT", "node_type": "net", "role": "output", "is_port": True, "degree": 2},
                {"id": "GND", "node_type": "net", "role": "ground", "is_port": True, "degree": 4},
                {"id": "net1", "node_type": "net", "role": "internal", "is_port": False, "degree": 4},
            ],
        }
        parasitic = {
            "schema_version": "parasitic_summary.v1",
            "case_name": "ota_core",
            "top_cell": "ota_core",
            "capacitor_count": 25,
            "total_cap_ff": 8.314394,
            "cap_by_net": {
                "VOUT": {"total_cap_ff": 0.571317, "capacitor_count": 6, "cap_rank": 5, "role": "output"},
                "VINP": {"total_cap_ff": 0.460555, "capacitor_count": 6, "cap_rank": 7, "role": "differential_input_plus"},
                "VINM": {"total_cap_ff": 0.462086, "capacitor_count": 6, "cap_rank": 6, "role": "differential_input_minus"},
                "IB": {"total_cap_ff": 0.429316, "capacitor_count": 4, "cap_rank": 8, "role": "unknown"},
                "a_25_264#": {"total_cap_ff": 1.939336, "capacitor_count": 7, "cap_rank": 3, "role": "unknown"},
            },
        }

        report = build_risk_report(graph, parasitic)

        self.assertEqual(report["schema_version"], "parasitic_risk_report.v1")
        self.assertEqual(report["case_name"], "ota_core")
        self.assertEqual(report["summary"]["max_severity"], "warning")
        self.assertEqual(report["summary"]["finding_count"], 4)
        self.assertIn("review_backend_layout", report["summary"]["recommended_actions"])
        by_rule = {finding["rule_id"]: finding for finding in report["findings"]}
        self.assertEqual(by_rule["output_node_cap"]["net"], "VOUT")
        self.assertEqual(by_rule["bias_node_cap"]["net"], "IB")
        self.assertLess(by_rule["differential_input_cap_mismatch"]["mismatch_ratio"], 0.01)
        self.assertEqual(by_rule["large_unmapped_extracted_net"]["severity"], "warning")


if __name__ == "__main__":
    unittest.main()
