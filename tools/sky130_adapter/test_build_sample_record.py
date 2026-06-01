#!/usr/bin/env python3
"""Tests for Sky130 graph-learning sample record generation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from build_sample_record import build_sample_record


class BuildSampleRecordTest(unittest.TestCase):
    def test_record_links_graph_pex_summary_and_pipeline_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            out_dir = root / "generated/sky130_cases/ota_core"
            case_dir = root / "generated/user_cases/ota_core"
            out_dir.mkdir(parents=True)
            case_dir.mkdir(parents=True)

            summary = out_dir / "summary.md"
            graph = out_dir / "circuit_graph.json"
            parasitic = out_dir / "parasitic_summary.json"
            gds = case_dir / "ota_core.sky130.pinned_shapes.gds"
            raw = out_dir / "ota_core_extracted.raw.spice"
            netlist = case_dir / "ota_core_magical.sp"
            for path in (gds, raw, netlist):
                path.write_text("placeholder\n", encoding="utf-8")
            graph.write_text('{"schema_version": "circuit_graph.v1"}\n', encoding="utf-8")
            parasitic.write_text(
                json.dumps(
                    {
                        "schema_version": "parasitic_summary.v1",
                        "capacitor_count": 25,
                        "total_cap_ff": 8.314394,
                    }
                ),
                encoding="utf-8",
            )
            summary.write_text(
                """
                # Sky130 Case Pipeline Summary

                | Field | Value |
                | --- | --- |
                | CASE_NAME | ota_core |
                | TOP_CELL | ota_core |
                | DRC_COUNT | 0 |
                | CONNECTIVITY_LVS_MATCH | yes |
                | PEX_CAPS | 25 |
                | PEX_TOTAL_CAP_FF | 8.31439 fF |
                """,
                encoding="utf-8",
            )

            record = build_sample_record(
                case_name="ota_core",
                top_cell="ota_core",
                vdd="VDD",
                vss="GND",
                case_dir=case_dir,
                out_dir=out_dir,
                source_netlist=netlist,
                final_gds=gds,
                raw_extracted_netlist=raw,
                circuit_graph=graph,
                parasitic_summary=parasitic,
                summary=summary,
                repo_root=root,
            )

        self.assertEqual(record["schema_version"], "pex_graph_sample.v1")
        self.assertEqual(record["case_name"], "ota_core")
        self.assertEqual(record["status"]["drc_count"], 0)
        self.assertEqual(record["status"]["connectivity_lvs_match"], True)
        self.assertEqual(record["status"]["pex_capacitor_count"], 25)
        self.assertEqual(record["status"]["pex_total_cap_ff"], 8.314394)
        self.assertEqual(record["artifacts"]["circuit_graph"], "generated/sky130_cases/ota_core/circuit_graph.json")
        self.assertEqual(record["artifacts"]["parasitic_summary"], "generated/sky130_cases/ota_core/parasitic_summary.json")
        self.assertEqual(record["training_sample"]["usable_for_graph_learning"], True)


if __name__ == "__main__":
    unittest.main()
