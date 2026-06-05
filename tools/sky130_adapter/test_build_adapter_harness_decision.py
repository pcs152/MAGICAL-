#!/usr/bin/env python3
"""Tests for AnalogGym adapter Harness decisions."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path("tools/sky130_adapter/build_adapter_harness_decision.py")


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class BuildAdapterHarnessDecisionTest(unittest.TestCase):
    def test_blocks_final_flow_but_allows_smoke_for_known_mim_capacitor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conversion_report = root / "conversion_report.json"
            output = root / "adapter_harness_decision.json"
            write_json(
                conversion_report,
                {
                    "schema_version": "analoggym_magical_conversion_report.v1",
                    "status": "blocked",
                    "top_cell": "Leung_DFCFC2_Pin_3",
                    "unsupported_instances": [
                        {
                            "name": "XC0",
                            "model": "sky130_fd_pr__cap_mim_m3_1",
                            "device_class": "capacitor",
                        }
                    ],
                    "omitted_instances": [],
                },
            )

            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--conversion-report",
                    str(conversion_report),
                    "--output",
                    str(output),
                ],
                cwd=Path(__file__).resolve().parents[2],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            decision = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(decision["schema_version"], "adapter_harness_decision.v1")
        self.assertEqual(decision["decision"], "block_final_flow")
        self.assertTrue(decision["smoke_allowed"])
        self.assertFalse(decision["final_flow_allowed"])
        self.assertEqual(decision["issues"][0]["issue_type"], "unsupported_device_model")
        self.assertEqual(decision["issues"][0]["known_category"], "mim_capacitor")
        self.assertIn("add_mim_cap_mapping", decision["issues"][0]["recommended_actions"])
        self.assertIn("block_final_pipeline_until_supported", decision["recommended_actions"])

    def test_marks_omit_with_report_conversion_as_smoke_only_not_final(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conversion_report = root / "conversion_report.json"
            output = root / "adapter_harness_decision.json"
            write_json(
                conversion_report,
                {
                    "schema_version": "analoggym_magical_conversion_report.v1",
                    "status": "converted",
                    "top_cell": "Leung_DFCFC2_Pin_3",
                    "unsupported_instances": [],
                    "omitted_instances": [
                        {
                            "name": "XC0",
                            "model": "sky130_fd_pr__cap_mim_m3_1",
                            "device_class": "capacitor",
                            "reason": "unsupported_model",
                        }
                    ],
                },
            )

            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--conversion-report",
                    str(conversion_report),
                    "--output",
                    str(output),
                ],
                cwd=Path(__file__).resolve().parents[2],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            decision = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(decision["decision"], "smoke_only_not_final")
        self.assertTrue(decision["smoke_allowed"])
        self.assertFalse(decision["final_flow_allowed"])
        self.assertEqual(decision["issues"][0]["source"], "omitted_instances")
        self.assertIn("do_not_use_for_final_performance", decision["recommended_actions"])

    def test_marks_mapped_mim_proxy_as_requiring_validation_not_final(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conversion_report = root / "conversion_report.json"
            output = root / "adapter_harness_decision.json"
            write_json(
                conversion_report,
                {
                    "schema_version": "analoggym_magical_conversion_report.v1",
                    "status": "converted",
                    "top_cell": "Leung_DFCFC2_Pin_3",
                    "unsupported_instances": [],
                    "omitted_instances": [],
                    "mapped_instances": [
                        {
                            "name": "XC0",
                            "source_model": "sky130_fd_pr__cap_mim_m3_1",
                            "target_model": "cfmom_2t",
                            "device_class": "capacitor",
                            "mapping_status": "needs_validation",
                        }
                    ],
                },
            )

            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--conversion-report",
                    str(conversion_report),
                    "--output",
                    str(output),
                ],
                cwd=Path(__file__).resolve().parents[2],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            decision = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(decision["decision"], "mapped_requires_validation")
        self.assertTrue(decision["smoke_allowed"])
        self.assertFalse(decision["final_flow_allowed"])
        self.assertEqual(decision["issues"][0]["issue_type"], "mapped_device_requires_validation")
        self.assertEqual(decision["issues"][0]["source"], "mapped_instances")
        self.assertEqual(decision["issues"][0]["known_category"], "mim_capacitor_proxy")
        self.assertIn("run_mim_proxy_drc_lvs_pex_validation", decision["recommended_actions"])

    def test_accepts_conversion_without_adapter_issues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conversion_report = root / "conversion_report.json"
            output = root / "adapter_harness_decision.json"
            write_json(
                conversion_report,
                {
                    "schema_version": "analoggym_magical_conversion_report.v1",
                    "status": "converted",
                    "top_cell": "small_case",
                    "converted_instances": [{"name": "M0"}],
                    "unsupported_instances": [],
                    "omitted_instances": [],
                },
            )

            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--conversion-report",
                    str(conversion_report),
                    "--output",
                    str(output),
                ],
                cwd=Path(__file__).resolve().parents[2],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            decision = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(decision["decision"], "accept_conversion")
        self.assertTrue(decision["smoke_allowed"])
        self.assertTrue(decision["final_flow_allowed"])
        self.assertEqual(decision["issues"], [])


if __name__ == "__main__":
    unittest.main()
