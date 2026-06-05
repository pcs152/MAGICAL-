#!/usr/bin/env python3
"""Tests for Sky130 environment diagnosis."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from diagnose_sky130_environment import analyze_magic_drc_log, build_diagnosis, render_markdown


class DiagnoseSky130EnvironmentTest(unittest.TestCase):
    def test_magic_log_identifies_pdk_techfile_parse_errors_and_segfault(self) -> None:
        analysis = analyze_magic_drc_log(
            """
            sky130A.tech: line 5438: section extract:
              Malformed line for keyword defaultsidewall.
            sky130A.tech: line 5974: section extract:
              Unrecognized layer (type) name "a1>0.99"
            Segmentation fault (core dumped)
            """
        )

        self.assertTrue(analysis["has_techfile_parse_errors"])
        self.assertTrue(analysis["has_segmentation_fault"])
        self.assertEqual(analysis["suspected_issue"], "magic_pdk_incompatibility")

    def test_build_diagnosis_reports_fail_for_known_magic_pdk_incompatibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sky130a = root / "versions/7b70722e33c03fcb5dabcf4d479fb0822d9251c9/sky130A"
            magic_dir = sky130a / "libs.tech/magic"
            netgen_dir = sky130a / "libs.tech/netgen"
            magic_dir.mkdir(parents=True)
            netgen_dir.mkdir(parents=True)
            (magic_dir / "sky130A.magicrc").write_text("# rc\n", encoding="utf-8")
            (magic_dir / "sky130A.tech").write_text("# tech\n", encoding="utf-8")
            (netgen_dir / "sky130A_setup.tcl").write_text("# setup\n", encoding="utf-8")
            drc_log = root / "magic_drc.log"
            drc_log.write_text("Malformed line for keyword defaultsidewall\nSegmentation fault\n", encoding="utf-8")
            summary = root / "summary.md"
            summary.write_text("| FAILED_STAGE | magic_drc |\n", encoding="utf-8")

            diagnosis = build_diagnosis(
                sky130a=sky130a,
                pdk_root=sky130a.parent,
                magic_version="8.3.105",
                magic_path="/usr/bin/magic",
                docker_version="Docker version 28.4.0",
                docker_path="/usr/bin/docker",
                netgen_path="/usr/bin/netgen-lvs",
                recent_magic_drc_log=drc_log,
                recent_summary=summary,
            )

        self.assertEqual(diagnosis["schema_version"], "sky130_environment_diagnosis.v1")
        self.assertEqual(diagnosis["environment_status"], "fail")
        self.assertEqual(diagnosis["pdk"]["hash"], "7b70722e33c03fcb5dabcf4d479fb0822d9251c9")
        self.assertEqual(diagnosis["suspected_issue"], "magic_pdk_incompatibility")
        self.assertIn("pin_compatible_magic_pdk_combo", diagnosis["recommended_next_actions"])

    def test_failed_magic_drc_summary_escalates_parse_errors_to_pipeline_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sky130a = root / "versions/7b70722e33c03fcb5dabcf4d479fb0822d9251c9/sky130A"
            magic_dir = sky130a / "libs.tech/magic"
            netgen_dir = sky130a / "libs.tech/netgen"
            magic_dir.mkdir(parents=True)
            netgen_dir.mkdir(parents=True)
            (magic_dir / "sky130A.magicrc").write_text("# rc\n", encoding="utf-8")
            (magic_dir / "sky130A.tech").write_text("# tech\n", encoding="utf-8")
            (netgen_dir / "sky130A_setup.tcl").write_text("# setup\n", encoding="utf-8")
            drc_log = root / "magic_drc.log"
            drc_log.write_text("Malformed line for keyword defaultsidewall\n", encoding="utf-8")
            summary = root / "summary.md"
            summary.write_text("| FAILED_STAGE | magic_drc |\n", encoding="utf-8")

            diagnosis = build_diagnosis(
                sky130a=sky130a,
                pdk_root=sky130a.parent,
                magic_version="8.3.105",
                magic_path="/usr/bin/magic",
                docker_version="Docker version 28.4.0",
                docker_path="/usr/bin/docker",
                netgen_path="/usr/bin/netgen-lvs",
                recent_magic_drc_log=drc_log,
                recent_summary=summary,
            )

        self.assertEqual(diagnosis["environment_status"], "fail")
        self.assertEqual(diagnosis["recent_pipeline_summary"]["failed_stage"], "magic_drc")
        self.assertEqual(diagnosis["impact"], "full_pipeline_blocked_but_v1_incremental_available")

    def test_render_markdown_contains_actionable_summary(self) -> None:
        markdown = render_markdown(
            {
                "environment_status": "fail",
                "suspected_issue": "magic_pdk_incompatibility",
                "tools": {"magic": {"version": "8.3.105", "path": "/usr/bin/magic"}},
                "pdk": {"hash": "7b70722e33c03fcb5dabcf4d479fb0822d9251c9", "sky130a": "/pdk/sky130A"},
                "recent_magic_drc_log": {"path": "/tmp/magic_drc.log"},
                "impact": "full_pipeline_blocked_but_v1_incremental_available",
                "recommended_next_actions": ["pin_compatible_magic_pdk_combo"],
            }
        )

        self.assertIn("Sky130 Environment Diagnosis", markdown)
        self.assertIn("magic_pdk_incompatibility", markdown)
        self.assertIn("full_pipeline_blocked_but_v1_incremental_available", markdown)


if __name__ == "__main__":
    unittest.main()
