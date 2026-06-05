#!/usr/bin/env python3
"""Tests for MAGICAL placement/routing log analysis."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path("tools/sky130_adapter/analyze_magical_route_log.py")


class AnalyzeMagicalRouteLogTest(unittest.TestCase):
    def test_reports_route_warning_even_when_route_gds_is_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "route.log"
            output = root / "route_report.json"
            log.write_text(
                "\n".join(
                    [
                        "DrGridRoute::runNRR\tIteration 0 Unrouted nets 15, vb4 dm_1 net31",
                        "DrGridAstar::run\tERROR: Route net net31 failed!",
                        "DrGridRoute::runNRR\tIteration 1 Unrouted nets 1, net31",
                        "DrGridRoute::solveDR Solved!!!!",
                        "PnR: routing finished  Leung_DFCFC2_Pin_3",
                        "Writing Routing GDS Layout ./Leung_DFCFC2_Pin_3.route.gds",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--log",
                    str(log),
                    "--output",
                    str(output),
                    "--case-name",
                    "amp_dfcfc2_rank1_mim_proxy",
                    "--top-cell",
                    "Leung_DFCFC2_Pin_3",
                ],
                cwd=Path(__file__).resolve().parents[2],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(report["status"], "completed_with_route_warnings")
        self.assertTrue(report["route_gds_written"])
        self.assertEqual(report["failed_route_nets"], ["net31"])
        self.assertEqual(report["last_unrouted_nets"], ["net31"])
        self.assertFalse(report["final_flow_allowed"])

    def test_accepts_clean_route_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "route.log"
            output = root / "route_report.json"
            log.write_text(
                "\n".join(
                    [
                        "DrGridRoute::solveDR Solved!!!!",
                        "PnR: routing finished  small_case",
                        "Writing Routing GDS Layout ./small_case.route.gds",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--log",
                    str(log),
                    "--output",
                    str(output),
                ],
                cwd=Path(__file__).resolve().parents[2],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(report["status"], "completed_clean")
        self.assertTrue(report["route_gds_written"])
        self.assertEqual(report["failed_route_nets"], [])
        self.assertTrue(report["final_flow_allowed"])

    def test_ignores_router_banner_text_after_unrouted_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "route.log"
            output = root / "route_report.json"
            log.write_text(
                "\n".join(
                    [
                        "DrGridRoute::runNRR\tIteration 0 Unrouted nets 2,Parsing LEF file sky130.lef",
                        "Writing Routing GDS Layout ./small_case.route.gds",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                ["python3", str(SCRIPT), "--log", str(log), "--output", str(output)],
                cwd=Path(__file__).resolve().parents[2],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(report["unrouted_iterations"][0]["nets"], [])
        self.assertNotIn("Parsing", report["last_unrouted_nets"])


if __name__ == "__main__":
    unittest.main()
