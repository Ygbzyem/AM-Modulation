"""Behavioral checks with known values, injected faults and synthetic spectra."""
import json
import hashlib
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np

from model.am_golden import Config, generate, save
from model.compare import compare, read_samples
from model.gen_sine_rom import generate_all, quarter_lookup, sine_tables
from model.run_part_a import cases
from model.spectrum import analyze_am, measure


def temporary_directory():
    root = Path(__file__).resolve().parents[1] / "results" / "test_tmp"
    root.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=root)


class RomTests(unittest.TestCase):
    def test_every_address_at_all_project_widths(self):
        for aw in (8, 10, 12):
            full, quarter = sine_tables(aw)
            self.assertEqual(len(quarter), (1 << aw) // 4)
            for address, value in enumerate(full):
                self.assertEqual(quarter_lookup(quarter, address, aw), value)
            self.assertEqual(full[:1 << (aw - 1)], [-v for v in full[1 << (aw - 1):]])

    def test_known_midpoint_values_and_boundaries(self):
        full, quarter = sine_tables(8)
        self.assertEqual([full[i] for i in (0, 63, 64, 127, 128, 191, 192, 255)],
                         [25, 2047, 2047, 25, -25, -2047, -2047, -25])

    def test_hex_files_decode_and_lengths(self):
        with temporary_directory() as directory:
            manifest = generate_all(directory)
            self.assertEqual(len(manifest["tables"]), 6)
            for record in manifest["tables"]:
                words = (Path(directory) / record["file"]).read_text().splitlines()
                self.assertEqual(hashlib.sha256((Path(directory) / record["file"]).read_bytes()).hexdigest(), record["sha256"])
                self.assertEqual(len(words), record["entries"])
                decoded = [int(word, 16) for word in words]
                decoded = [v - 4096 if v >= 2048 else v for v in decoded]
                expected = sine_tables(record["aw"])[record["architecture"] == "QUARTER"]
                self.assertEqual(decoded, expected)


class GoldenTests(unittest.TestCase):
    def test_known_first_samples_phase_before_increment(self):
        rows = generate(Config(samples=2))
        self.assertEqual([row["phase_car"] for row in rows], [0, 42_949_673])
        self.assertEqual([row["car"] for row in rows], [25, 126])
        self.assertEqual([row["msg"] for row in rows], [25, 25])
        self.assertEqual([row["env"] for row in rows], [2012, 2012])
        self.assertEqual([row["out"] for row in rows], [24, 123])

    def test_signed_shift_at_extrema(self):
        config = Config(samples=1, initial_phase_car=63 << 24,
                        initial_phase_msg=63 << 24)
        positive = generate(config)[0]
        negative = generate(replace(config, initial_phase_msg=191 << 24))[0]
        self.assertEqual((positive["msg"], positive["msg_term"], positive["env"], positive["out"]),
                         (2047, 999, 2999, 2997))
        self.assertEqual((negative["msg"], negative["msg_term"], negative["env"]), (-2047, -1000, 1000))

    def test_phase_wrap_and_start_sample(self):
        config = Config(pw=8, aw=8, ftw_car=255, ftw_msg=1, samples=4,
                        initial_phase_car=1, initial_phase_msg=254)
        rows = generate(config)
        self.assertEqual([row["phase_car"] for row in rows], [1, 0, 255, 254])
        self.assertEqual([row["phase_msg"] for row in rows], [254, 255, 0, 1])
        advanced = generate(replace(config, start_sample=2, samples=2))
        self.assertEqual(advanced, rows[2:])

    def test_full_quarter_all_cases(self):
        self.assertEqual(len(cases()), 13)
        for name, config in cases():
            self.assertEqual(generate(replace(config, rom_arch="FULL")),
                             generate(replace(config, rom_arch="QUARTER")), name)

    def test_default_envelope_and_overmodulation(self):
        for amplitude, limits in ((0, (2000, 2000)), (500, (1500, 2499)),
                                  (1000, (1000, 2999)), (2000, (0, 3999)),
                                  (3000, (-999, 4998))):
            env = [row["env"] for row in generate(Config(amp_msg=amplitude))]
            self.assertEqual((min(env), max(env)), limits)

    def test_max_input_range_no_overflow(self):
        rows = generate(Config(amp_car=4095, amp_msg=4095, aw=12))
        self.assertTrue(all(-8192 <= row["env"] <= 8191 and -32768 <= row["out"] <= 32767 for row in rows))

    def test_parameter_validation(self):
        for options in ({"amp_msg": -1}, {"amp_car": 4096}, {"samples": 0}, {"ftw_car": 1 << 32},
                        {"start_sample": -1}, {"dw": 10}, {"rom_arch": "TYPO"}):
            with self.assertRaises(ValueError):
                Config(**options)

    def test_saved_file_and_metadata(self):
        with temporary_directory() as directory:
            root = Path(directory)
            save(Config(), root / "golden.txt", root / "trace.csv", root / "metadata.json")
            self.assertEqual(len(read_samples(root / "golden.txt")), 10_000)
            self.assertEqual(json.loads((root / "metadata.json").read_text())["env_min"], 1000)


class CompareTests(unittest.TestCase):
    def check_streams(self, golden, rtl, **options):
        with temporary_directory() as directory:
            first, second = Path(directory) / "g.txt", Path(directory) / "r.txt"
            first.write_text(golden, encoding="utf-8")
            second.write_text(rtl, encoding="utf-8")
            return compare(first, second, **options)

    def test_pass(self):
        result = self.check_streams("1\n-2\n0\n", "1\n-2\n0\n", expected_samples=3)
        self.assertTrue(result["passed"])

    def test_single_lsb_fault_has_location_and_error(self):
        result = self.check_streams("1\n-2\n0\n", "1\n-1\n0\n", expected_samples=3)
        self.assertFalse(result["passed"])
        self.assertEqual(result["mismatches"], 1)
        self.assertEqual(result["first_mismatch"]["index"], 1)
        self.assertEqual(result["max_abs_error"], 1)

    def test_truncation_and_extra_data_fail(self):
        self.assertEqual(self.check_streams("1\n2\n", "1\n", expected_samples=2)["missing_samples"], 1)
        result = self.check_streams("1\n", "1\n2\n", expected_samples=1)
        self.assertFalse(result["passed"])
        self.assertEqual(result["extra_samples"], 1)
        self.assertFalse(self.check_streams("1\n", "1\n")["passed"])

    def test_unknown_out_of_range_and_empty_fail(self):
        for rtl in ("X\n", "12z\n", "32768\n", "-32769\n", "", "1 2\n", "1.0\n"):
            result = self.check_streams("1\n", rtl, expected_samples=1)
            self.assertFalse(result["passed"])
            self.assertIsNotNone(result["error"])

    def test_explicit_warmup_only(self):
        self.assertFalse(self.check_streams("1\n2\n", "0\n1\n2\n", expected_samples=2)["passed"])
        result = self.check_streams("1\n2\n", "0\n1\n2\n", skip_rtl=1, expected_samples=2)
        self.assertTrue(result["passed"])

    def test_missing_file_is_fail(self):
        result = compare("file_that_does_not_exist_01.txt", "file_that_does_not_exist_02.txt")
        self.assertFalse(result["passed"])
        self.assertIsNotNone(result["error"])


class SpectrumTests(unittest.TestCase):
    def test_known_spur_60_db(self):
        n = np.arange(10_000)
        values = np.sin(2 * np.pi * 0.01 * n) + 0.001 * np.sin(2 * np.pi * 0.02 * n)
        result = measure(values, 100_000_000, [1_000_000])
        self.assertAlmostEqual(result["sfdr_db"], 60, places=7)
        self.assertEqual(result["largest_spur_hz"], 2_000_000)

    def test_sidebands_are_wanted_not_spurs(self):
        n = np.arange(10_000)
        values = (1 + 0.5 * np.cos(2 * np.pi * 0.0002 * n)) * np.cos(2 * np.pi * 0.01 * n)
        values += 0.001 * np.cos(2 * np.pi * 0.02 * n)
        result = analyze_am(values, Config())
        self.assertAlmostEqual(result["sfdr_db"], 60, places=6)
        for line in result["lines"]:
            if line["label"] != "carrier":
                self.assertAlmostEqual(line["ratio_to_carrier"], 0.25, places=7)

    def test_dsb_sc_ratio_undefined(self):
        config = Config(amp_car=0)
        result = analyze_am([row["out"] for row in generate(config)], config)
        self.assertIsNone(result["mu"])
        self.assertEqual(len(result["wanted_tones"]), 2)
        self.assertTrue(all(line["ratio_to_carrier"] is None for line in result["lines"]))

    def test_short_record_rejected_for_am(self):
        with self.assertRaises(ValueError):
            analyze_am([1] * 100, Config(samples=100))


if __name__ == "__main__":
    unittest.main()
