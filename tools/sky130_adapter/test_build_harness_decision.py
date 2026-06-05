#!/usr/bin/env python3
"""Tests for V1 Harness diagnostic decision generation."""

from __future__ import annotations

import unittest

from build_harness_decision import build_harness_decision


class BuildHarnessDecisionTest(unittest.TestCase):
    def test_warning_risk_report_requests_backend_review_without_rejecting_sample(self) -> None:
        risk_report = {
            "schema_version": "parasitic_risk_report.v1",
            "case_name": "ota_core",
            "summary": {
                "max_severity": "warning",
                "recommended_actions": ["review_backend_layout", "record_as_training_sample"],
            },
            "findings": [
                {
                    "rule_id": "large_unmapped_extracted_net",
                    "severity": "warning",
                    "net": "a_25_264#",
                    "suggested_action": "review_backend_layout",
                }
            ],
        }
        sample_record = {
            "schema_version": "pex_graph_sample.v1",
            "case_name": "ota_core",
            "status": {
                "drc_count": 0,
                "connectivity_lvs_match": True,
                "pex_capacitor_count": 25,
            },
            "training_sample": {"usable_for_graph_learning": True},
        }

        decision = build_harness_decision(risk_report, sample_record)

        self.assertEqual(decision["schema_version"], "harness_decision.v1")
        self.assertEqual(decision["case_name"], "ota_core")
        self.assertEqual(decision["decision"], "review_with_warnings")
        self.assertTrue(decision["usable_for_training"])
        self.assertIn("review_backend_layout", decision["recommended_actions"])

    def test_failed_pipeline_artifact_blocks_training(self) -> None:
        decision = build_harness_decision(
            {"case_name": "broken", "summary": {"max_severity": "observation"}, "findings": []},
            {
                "case_name": "broken",
                "status": {"drc_count": "unknown", "connectivity_lvs_match": False, "pex_capacitor_count": "unknown"},
                "training_sample": {"usable_for_graph_learning": False},
            },
        )

        self.assertEqual(decision["decision"], "reject_pipeline_artifact")
        self.assertFalse(decision["usable_for_training"])
        self.assertIn("fix_pipeline_artifact", decision["recommended_actions"])


if __name__ == "__main__":
    unittest.main()
