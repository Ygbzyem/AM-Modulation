"""Worst-case widths of the fixed-point datapath, for every legal input.

The RTL keeps msg_term and env in 14 signed bits and am_out in 16 signed bits.
Each stage is monotonic in its inputs, so the extremes occur at the corners:
amp_* in {0, 4095} and the sine sample at its table minimum or maximum. These
tests sweep every amp_msg value against those corners and assert that no stage
can overflow, then check that Python >> matches Verilog >>> (floor) on the
negative side, which is the case that breaks if the signed cast is missing.
"""
import unittest

from golden_model.gen_sine_rom import sine_tables

ENV_MIN, ENV_MAX = -(1 << 13), (1 << 13) - 1      # 14-bit signed
OUT_MIN, OUT_MAX = -(1 << 15), (1 << 15) - 1      # 16-bit signed


def table_extremes():
    lows, highs = [], []
    for aw in (8, 10, 12):
        full, _ = sine_tables(aw, 12)
        lows.append(min(full))
        highs.append(max(full))
    return min(lows), max(highs)


class DatapathRanges(unittest.TestCase):
    def test_table_stays_inside_12_bits(self):
        low, high = table_extremes()
        self.assertGreaterEqual(low, -2048)
        self.assertLessEqual(high, 2047)

    def test_no_stage_can_overflow(self):
        low, high = table_extremes()
        env_seen, out_seen = [], []
        for amp_msg in range(4096):
            for msg in (low, high):
                msg_term = (amp_msg * msg) >> 11
                self.assertTrue(ENV_MIN <= msg_term <= ENV_MAX)
                for amp_car in (0, 4095):
                    env = amp_car + msg_term
                    self.assertTrue(ENV_MIN <= env <= ENV_MAX, (amp_car, amp_msg, msg))
                    env_seen.append(env)
                    for car in (low, high):
                        out = (env * car) >> 11
                        self.assertTrue(OUT_MIN <= out <= OUT_MAX, (amp_car, amp_msg, msg, car))
                        out_seen.append(out)
        # documented bounds, useful for the README
        self.assertEqual((min(env_seen), max(env_seen)), (-4094, 4095 + 4093))
        self.assertLess(max(abs(v) for v in out_seen), 1 << 14)

    def test_shift_is_floor_not_truncation(self):
        # Verilog >>> on a signed value rounds toward -inf, like Python >>.
        self.assertEqual((-1000 * 2047) >> 11, -1000)
        self.assertEqual(int(-1000 * 2047 / 2048), -999)    # truncation would differ


if __name__ == "__main__":
    unittest.main()
