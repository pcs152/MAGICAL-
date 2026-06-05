#!/usr/bin/env python3
"""Tests for converting AnalogGym Sky130 netlists into MAGICAL-readable netlists."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path("tools/sky130_adapter/convert_analoggym_sky130_netlist.py")


AMP_DFCFC2_MINI_NETLIST = """
.subckt Leung_DFCFC2_Pin_3 gnda vdda vinn vinp vout Ib
XM0 vout Ib vdda vdda sky130_fd_pr__pfet_01v8 l=L_M0 w='W_M0*1' nf=2 m='2*M_M0'
XM1 vout vinn gnda gnda sky130_fd_pr__nfet_01v8 l=L_M1 w=W_M1 nf=2 m=M_M1
XC0 vout net050 sky130_fd_pr__cap_mim_m3_1 W=30 L=30 MF=M_C0 m=M_C0
.ends Leung_DFCFC2_Pin_3
"""


AMP_DFCFC2_MINI_VARS = """
.param W_M0=1.5
.param L_M0=1.0
.param M_M0=4
.param W_M1=2.0
.param L_M1=0.5
.param M_M1=3
.param M_C0=10
"""


class ConvertAnalogGymSky130NetlistTest(unittest.TestCase):
    def test_block_policy_reports_unsupported_mim_capacitor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_netlist = root / "amp_dfcfc2.sp"
            vars_path = root / "amp_dfcfc2_vars.spice"
            output_netlist = root / "amp_dfcfc2_magical.sp"
            report = root / "conversion_report.json"
            input_netlist.write_text(AMP_DFCFC2_MINI_NETLIST, encoding="utf-8")
            vars_path.write_text(AMP_DFCFC2_MINI_VARS, encoding="utf-8")

            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--input",
                    str(input_netlist),
                    "--vars",
                    str(vars_path),
                    "--output",
                    str(output_netlist),
                    "--report",
                    str(report),
                    "--unsupported-cap-policy",
                    "block",
                ],
                cwd=Path(__file__).resolve().parents[2],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sky130_fd_pr__cap_mim_m3_1", result.stderr + result.stdout)
        self.assertIn("unsupported", result.stderr.lower() + result.stdout.lower())

    def test_omit_with_report_policy_writes_mos_only_magical_netlist_and_records_omitted_cap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_netlist = root / "amp_dfcfc2.sp"
            vars_path = root / "amp_dfcfc2_vars.spice"
            output_netlist = root / "amp_dfcfc2_magical.sp"
            report = root / "conversion_report.json"
            input_netlist.write_text(AMP_DFCFC2_MINI_NETLIST, encoding="utf-8")
            vars_path.write_text(AMP_DFCFC2_MINI_VARS, encoding="utf-8")

            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--input",
                    str(input_netlist),
                    "--vars",
                    str(vars_path),
                    "--output",
                    str(output_netlist),
                    "--report",
                    str(report),
                    "--unsupported-cap-policy",
                    "omit-with-report",
                ],
                cwd=Path(__file__).resolve().parents[2],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            converted = output_netlist.read_text(encoding="utf-8")
            conversion_report = report.read_text(encoding="utf-8")

        self.assertIn("subckt Leung_DFCFC2_Pin_3 gnda vdda vinn vinp vout Ib", converted)
        self.assertIn("M0 (vout Ib vdda vdda) sky130_fd_pr__pfet_01v8 l=1u w=1.5u multi=8 nf=2", converted)
        self.assertIn("M1 (vout vinn gnda gnda) sky130_fd_pr__nfet_01v8 l=500n w=2u multi=3 nf=2", converted)
        self.assertNotIn("XC0", converted)
        self.assertIn("sky130_fd_pr__cap_mim_m3_1", conversion_report)
        self.assertIn("omitted_instances", conversion_report)

    def test_map_mim_policy_writes_cfmom_2t_proxy_and_records_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_netlist = root / "amp_dfcfc2.sp"
            vars_path = root / "amp_dfcfc2_vars.spice"
            output_netlist = root / "amp_dfcfc2_magical.sp"
            report = root / "conversion_report.json"
            input_netlist.write_text(AMP_DFCFC2_MINI_NETLIST, encoding="utf-8")
            vars_path.write_text(AMP_DFCFC2_MINI_VARS, encoding="utf-8")

            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--input",
                    str(input_netlist),
                    "--vars",
                    str(vars_path),
                    "--output",
                    str(output_netlist),
                    "--report",
                    str(report),
                    "--unsupported-cap-policy",
                    "map-mim-to-cfmom-2t",
                ],
                cwd=Path(__file__).resolve().parents[2],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            converted = output_netlist.read_text(encoding="utf-8")
            conversion_report = report.read_text(encoding="utf-8")

        self.assertIn("C0 (vout net050) cfmom_2t", converted)
        self.assertIn("nr=10", converted)
        self.assertIn("lr=30u", converted)
        self.assertIn("w=70n s=70n stm=2 spm=6 multi=10 ftip=140n", converted)
        self.assertIn('"mapped_instances"', conversion_report)
        self.assertIn('"source_model": "sky130_fd_pr__cap_mim_m3_1"', conversion_report)
        self.assertIn('"target_model": "cfmom_2t"', conversion_report)
        self.assertIn('"mapping_status": "needs_validation"', conversion_report)


if __name__ == "__main__":
    unittest.main()
