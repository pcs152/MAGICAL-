#!/usr/bin/env python3
"""Tests for materializing AnalogGym candidate actions into vars spice files."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path("tools/sky130_adapter/materialize_analoggym_candidate_vars.py")


MINI_CONFIG = """
device:
  M0:
    range:
      W: [0.5, 10]
      L: [0.5, 5]
      M: [1, 50]
    init: {W: 1, L: 1, M: 4}
  Ib:
    range:
      I: [1e-6, 30e-6]
    init: {I: 1e-5}
  C0:
    range:
      M: [1, 30]
    init: {M: 10}
"""


class MaterializeAnalogGymCandidateVarsTest(unittest.TestCase):
    def test_writes_vars_file_from_ranked_candidate_action_real(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "amp_case.yaml"
            candidates = root / "recommended_candidates.json"
            output = root / "rank1_vars.spice"
            metadata = root / "rank1_vars_metadata.json"
            config.write_text(MINI_CONFIG, encoding="utf-8")
            candidates.write_text(
                json.dumps(
                    [
                        {
                            "rank": 1,
                            "reward": -0.75,
                            "pm_feasible": True,
                            "evaluation_source": "tt",
                            "action_real": [5.3, 2.7, 25.0, 1.55e-05, 15.0],
                            "performance": {"phase_margin (deg)": 76.8},
                        }
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--config",
                    str(config),
                    "--candidates",
                    str(candidates),
                    "--rank",
                    "1",
                    "--output",
                    str(output),
                    "--metadata-output",
                    str(metadata),
                ],
                cwd=Path(__file__).resolve().parents[2],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            vars_text = output.read_text(encoding="utf-8")
            meta = json.loads(metadata.read_text(encoding="utf-8"))

        self.assertIn(".param W_M0=5.3", vars_text)
        self.assertIn(".param L_M0=2.7", vars_text)
        self.assertIn(".param M_M0=25", vars_text)
        self.assertIn(".param I_Ib=1.55e-05", vars_text)
        self.assertIn(".param M_C0=15", vars_text)
        self.assertEqual(meta["status"], "materialized")
        self.assertEqual(meta["selected_candidate"]["rank"], 1)
        self.assertEqual(meta["selected_candidate"]["evaluation_source"], "tt")
        self.assertEqual(meta["parameter_count"], 5)
        self.assertEqual(meta["parameter_order"], ["W_M0", "L_M0", "M_M0", "I_Ib", "M_C0"])

    def test_rejects_candidate_when_action_length_does_not_match_config_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "amp_case.yaml"
            candidates = root / "recommended_candidates.json"
            output = root / "rank1_vars.spice"
            metadata = root / "rank1_vars_metadata.json"
            config.write_text(MINI_CONFIG, encoding="utf-8")
            candidates.write_text(json.dumps([{"rank": 1, "action_real": [5.3, 2.7]}]), encoding="utf-8")

            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--config",
                    str(config),
                    "--candidates",
                    str(candidates),
                    "--rank",
                    "1",
                    "--output",
                    str(output),
                    "--metadata-output",
                    str(metadata),
                ],
                cwd=Path(__file__).resolve().parents[2],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("action_real length", result.stderr + result.stdout)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
