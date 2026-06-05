#!/usr/bin/env python3
"""Static safety tests for Sky130 pipeline environment selection."""

from __future__ import annotations

import unittest
from pathlib import Path


SCRIPT = Path("tools/sky130_adapter/run_sky130_case_pipeline.sh")


class RunSky130CasePipelineEnvTest(unittest.TestCase):
    def test_pipeline_prefers_iot_magic_wrapper_and_checks_minimum_magic_version(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("IOT_ENV_SCRIPT", text)
        self.assertIn("magical_sky130_env.sh", text)
        self.assertIn("IOT_ENV_BIN", text)
        self.assertIn("scripts/env/bin", text)
        self.assertIn("version_ge", text)
        self.assertIn("magic --version", text)
        self.assertIn("8.3.411", text)
        self.assertIn("Magic version", text)

    def test_pipeline_preserves_detailed_summary_when_late_stage_fails(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")

        self.assertIn('if [[ -f "$SUMMARY" ]]', text)
        self.assertIn("## FAILURE", text)
        self.assertIn("FAILED_STAGE", text)

    def test_pipeline_marks_power_and_ground_roles_in_pex_summary(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")

        self.assertIn('--net-role "$VDD_NET=power"', text)
        self.assertIn('--net-role "$VSS_NET=ground"', text)


if __name__ == "__main__":
    unittest.main()
