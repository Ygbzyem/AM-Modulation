"""Checks for the implementation scripts: Vivado report parsing, cases.yaml, run_experiments helpers, Excel output."""
import re
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import run_experiments as rx      # noqa: E402
import vivado_reports as vr       # noqa: E402
import write_excel                # noqa: E402
from model.run_part_a import cases as reference_cases   # noqa: E402

UTIL = """\
| Slice LUTs*                |  123 |     0 |          0 |     20800 |  0.59 |
|   LUT as Logic             |  100 |     0 |          0 |     20800 |  0.48 |
|   LUT as Memory            |   23 |     0 |          0 |      9600 |  0.24 |
| Slice Registers            |  200 |     0 |          0 |     41600 |  0.48 |
| Block RAM Tile    |  0.5 |     0 |          0 |        50 |  1.00 |
| DSPs           |    2 |     0 |          0 |        90 |  2.22 |
"""
TIMING = """\
    WNS(ns)      TNS(ns)  TNS Failing Endpoints  TNS Total Endpoints      WHS(ns)      THS(ns)  THS Failing Endpoints  THS Total Endpoints     WPWS(ns)     TPWS(ns)  TPWS Failing Endpoints  TPWS Total Endpoints
    -------      -------  ---------------------  -------------------      -------      -------  ---------------------  -------------------     --------     --------  ----------------------  --------------------
      2.000        0.000                      0                  250        0.150        0.000                      0                  250        4.500        0.000                      0                  120
"""
POWER = """\
| Total On-Chip Power (W)  | 0.123        |
| Dynamic (W)              | 0.050        |
| Device Static (W)        | 0.073        |
"""


def write_reports(directory, util=UTIL, timing=TIMING, power=POWER):
    directory = Path(directory)
    (directory / "utilization.rpt").write_text(util)
    (directory / "timing.rpt").write_text(timing)
    (directory / "power.rpt").write_text(power)


class ReportParserTests(unittest.TestCase):
    def test_known_values(self):
        with tempfile.TemporaryDirectory() as d:
            write_reports(d)
            r = vr.parse_impl_dir(d)
        self.assertEqual((r["lut"], r["lut_logic"], r["lutram"], r["ff"], r["dsp"]), (123, 100, 23, 200, 2))
        self.assertEqual(r["bram"], 0.5)
        self.assertEqual(r["wns"], 2.0)
        self.assertAlmostEqual(r["fmax_mhz"], 125.0)
        self.assertAlmostEqual(r["power_dynamic_w"], 0.05)

    def test_fmax_formula(self):
        self.assertAlmostEqual(vr.fmax_mhz(2.0), 125.0)
        self.assertAlmostEqual(vr.fmax_mhz(0.0), 100.0)
        self.assertLess(vr.fmax_mhz(-1.0), 100.0)

    def test_negative_wns(self):
        with tempfile.TemporaryDirectory() as d:
            write_reports(d, timing=TIMING.replace("2.000", "-0.500"))
            self.assertEqual(vr.parse_timing(Path(d) / "timing.rpt")["wns"], -0.5)

    def test_missing_field_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            write_reports(d, util=UTIL.replace("DSPs", "Xxx"))
            with self.assertRaises(ValueError):
                vr.parse_utilization(Path(d) / "utilization.rpt")
            write_reports(d, timing="nothing\n")
            with self.assertRaises(ValueError):
                vr.parse_timing(Path(d) / "timing.rpt")


class CasesFileTests(unittest.TestCase):
    def setUp(self):
        self.cases = rx.load_cases(ROOT / "scripts" / "cases.yaml")

    def test_matches_reference_cases(self):
        reference = reference_cases()
        self.assertEqual([c["id"] for c in self.cases], [name for name, _ in reference])
        for case, (_, config) in zip(self.cases, reference):
            self.assertEqual(rx.case_config(case), config, case["id"])

    def test_groups_and_impl_tags(self):
        self.assertEqual([c["group"] for c in self.cases], ["functional"] * 7 + ["resource"] * 6)
        for c in self.cases[7:]:
            self.assertEqual(c["impl_tag"], f"AW{c['aw']}_{c['rom_arch']}")
        for c in self.cases[:7]:
            self.assertEqual(c["impl_tag"], "AW8_FULL")

    def test_frequency_tuning_words(self):
        self.assertEqual(self.cases[0]["ftw_car"], round(1e6 * 2**32 / 1e8))
        self.assertEqual(self.cases[0]["ftw_msg"], round(20e3 * 2**32 / 1e8))
        self.assertEqual(self.cases[6]["ftw_msg"], round(100e3 * 2**32 / 1e8))


class TestbenchCopyTests(unittest.TestCase):
    def test_instance_and_length_are_rewritten(self):
        case = {**rx.load_cases(ROOT / "scripts" / "cases.yaml", ["rom_aw10_quarter"])[0]}
        with tempfile.TemporaryDirectory() as d:
            text = rx.make_testbench(case, Path(d)).read_text()
        self.assertRegex(text, r"am_modulator_top #\(\.AW\(10\), \.USE_QUARTER_ROM\(1\)")
        self.assertIn("i < 10003", text)
        self.assertEqual(len(re.findall(r"u_dut\s*\(", text)), 1)


class ExcelTests(unittest.TestCase):
    def test_three_sheets(self):
        row = {"case_id": "c", "group": "functional", "note": "n", "aw": 8, "rom_arch": "FULL",
               "ftw_car": 1, "ftw_msg": 1, "amp_car": 2000, "amp_msg": 0, "mu": 0.0, "f_msg_hz": 2e4,
               "bandwidth_hz": 0.0, "env_min": 2000, "env_max": 2000, "out_min": -1, "out_max": 1,
               "result": "PASS", "mismatch_count": 0, "latency": 3, "sfdr_db": float("nan"),
               "lut": 1, "ff": 2, "lutram": 0, "bram": 0.5, "dsp": 2, "wns": 2.0, "fmax_mhz": 125.0,
               "power_dynamic_w": 0.05, "rpt_dir": "results/rpt/AW8_FULL", "figures": {},
               "spectrum": [{"label": "carrier", "expected_hz": 1e6, "measured_bin_hz": 1e6,
                             "freq_error_hz": 0.0, "peak_amplitude": 1998.0, "ratio_to_carrier": 1.0,
                             "ideal_ratio_to_carrier": 1.0, "ratio_error": 0.0}]}
        with tempfile.TemporaryDirectory() as d:
            out = write_excel.build([row], Path(d) / "r.xlsx", ROOT)
            import openpyxl
            wb = openpyxl.load_workbook(out)
        self.assertEqual(wb.sheetnames, ["Summary", "Figures", "Spectrum"])
        header = [c.value for c in wb["Summary"][1]]
        self.assertIsNone(wb["Summary"].cell(row=2, column=header.index("SFDR (dB)") + 1).value)
        self.assertEqual(wb["Spectrum"].max_row, 2)


if __name__ == "__main__":
    unittest.main()
