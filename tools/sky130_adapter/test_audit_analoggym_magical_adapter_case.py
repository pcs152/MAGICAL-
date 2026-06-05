#!/usr/bin/env python3
"""Tests for AnalogGym-to-MAGICAL adapter readiness audit."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from audit_analoggym_magical_adapter_case import build_audit


class AuditAnalogGymMagicalAdapterCaseTest(unittest.TestCase):
    def test_audit_resolves_symbolic_mos_params_and_flags_mim_cap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            netlist = root / "case.sp"
            vars_path = root / "case_vars.spice"
            netlist.write_text(
                """
.subckt Leung_DFCFC2_Pin_3 gnda vdda vinn vinp vout Ib
XM0 vout Ib vdda vdda sky130_fd_pr__pfet_01v8 l=L_M0 w='W_M0*1' nf=2 m='2*M_M0'
XM1 vout vinn gnda gnda sky130_fd_pr__nfet_01v8 l=L_M1 w=W_M1 nf=2 m=M_M1
XC0 vout net050 sky130_fd_pr__cap_mim_m3_1 W=30 L=30 MF=M_C0 m=M_C0
.ends Leung_DFCFC2_Pin_3
""",
                encoding="utf-8",
            )
            vars_path.write_text(
                """
.param W_M0=1.5
.param L_M0=1.0
.param M_M0=4
.param W_M1=2.0
.param L_M1=0.5
.param M_M1=3
.param M_C0=10
""",
                encoding="utf-8",
            )

            audit = build_audit("amp_dfcfc2", netlist, vars_path, None)

        self.assertEqual(audit["top_cell"], "Leung_DFCFC2_Pin_3")
        self.assertEqual(audit["device_counts"]["pfet"], 1)
        self.assertEqual(audit["device_counts"]["nfet"], 1)
        self.assertEqual(audit["device_counts"]["capacitor"], 1)
        self.assertEqual(audit["unresolved_param_count"], 0)
        self.assertEqual(audit["unsupported_models"], {"sky130_fd_pr__cap_mim_m3_1": 1})
        self.assertEqual(audit["readiness"], "blocked")
        self.assertEqual(audit["port_roles"]["vout"], "output")
        self.assertEqual(audit["port_roles"]["vinp"], "differential_input_plus")
        self.assertEqual(audit["port_roles"]["vinn"], "differential_input_minus")
        self.assertEqual(audit["port_roles"]["vdda"], "power")
        self.assertEqual(audit["port_roles"]["gnda"], "ground")
        self.assertIn("unsupported_device_models", {item["id"] for item in audit["blockers"]})


if __name__ == "__main__":
    unittest.main()
