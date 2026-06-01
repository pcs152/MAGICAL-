#!/usr/bin/env python3
"""Tests for Magic PEX summary helpers."""

from __future__ import annotations

import unittest

from summarize_magic_pex import build_json_summary, parse_caps, render_summary


class SummarizeMagicPexTest(unittest.TestCase):
    def test_render_summary_includes_output_node_estimate(self) -> None:
        caps = parse_caps(["C0 VOUT GND 2f", "C1 VOUT VDD 3f", "C2 A GND 1f"])

        markdown = render_summary(caps, "example.spice", top=10, output_node="VOUT")

        self.assertIn("## Output Node Estimate", markdown)
        self.assertIn("| `VOUT` | 2 | 5 fF |", markdown)
        self.assertIn("| `GND` | 2 | 3 fF |", markdown)

    def test_build_json_summary_reports_core_capacitance_fields(self) -> None:
        caps = parse_caps(["C0 VOUT GND 2f", "C1 VOUT VDD 3f", "C2 VINP VINM 1f"])

        summary = build_json_summary(
            caps,
            input_name="example.spice",
            case_name="demo_case",
            top_cell="demo_top",
            top=2,
            net_roles={"VOUT": "output", "VINP": "differential_input_plus", "VINM": "differential_input_minus"},
        )

        self.assertEqual(summary["schema_version"], "parasitic_summary.v1")
        self.assertEqual(summary["case_name"], "demo_case")
        self.assertEqual(summary["top_cell"], "demo_top")
        self.assertEqual(summary["capacitor_count"], 3)
        self.assertAlmostEqual(summary["total_cap_ff"], 6.0)
        self.assertEqual(summary["cap_by_net"]["VOUT"]["capacitor_count"], 2)
        self.assertAlmostEqual(summary["cap_by_net"]["VOUT"]["total_cap_ff"], 5.0)
        self.assertEqual(summary["top_caps"][0]["name"], "C1")

    def test_build_json_summary_flags_output_cap_rank(self) -> None:
        caps = parse_caps(["C0 VOUT GND 2f", "C1 VOUT VDD 3f", "C2 A GND 1f"])

        summary = build_json_summary(caps, input_name="example.spice", output_node="VOUT")

        self.assertEqual(summary["net_roles"]["VOUT"], "output")
        self.assertEqual(summary["rule_hits"][0]["rule_id"], "output_node_cap_rank")
        self.assertEqual(summary["rule_hits"][0]["net"], "VOUT")
        self.assertEqual(summary["rule_hits"][0]["suggested_action"], "review_backend_then_frontend")


if __name__ == "__main__":
    unittest.main()
