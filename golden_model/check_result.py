"""Compare the Vivado simulation output against the Python golden model.

This file lives in golden_model/ and is run from the repository root:

    python golden_model/check_result.py
    python golden_model/check_result.py results/am_out.txt
    python golden_model/check_result.py results/am_out.txt --latency 3

Exit code: 0 = bit-exact match, 1 = mismatch, 2 = a file was missing.
"""

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # golden_model/
ROOT = HERE.parent                              # repository root
LATENCY = 3                                     # 2 ROM stages + 1 multiplier stage

# the reference model uses a relative import, so both paths must be importable
for entry in (str(HERE), str(ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

try:
    from am_golden import Config, generate
except ImportError:
    from golden_model.am_golden import Config, generate


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("rtl_file", nargs="?", default="results/am_out.txt",
                        help="file written by the Vivado testbench")
    parser.add_argument("--latency", type=int, default=LATENCY,
                        help="number of leading RTL samples to drop")
    args = parser.parse_args()

    rtl_path = Path(args.rtl_file)
    if not rtl_path.is_absolute():
        rtl_path = ROOT / rtl_path
    if not rtl_path.exists():
        print(f"ERROR: {rtl_path} not found. Run the simulation in Vivado first.")
        return 2

    raw = rtl_path.read_text(encoding="utf-8-sig").split()
    if any(ch in {"x", "X", "z", "Z"} for token in raw for ch in token):
        print(f"ERROR: {rtl_path} contains X or Z values.")
        print("       The sine ROM was not loaded: check the .mem paths in src/.")
        return 2

    rtl = [int(token) for token in raw]
    golden = [row["out"] for row in generate(Config())]

    print(f"RTL file      : {rtl_path}")
    print(f"RTL samples   : {len(rtl)}")
    print(f"Golden samples: {len(golden)}")
    print(f"Latency       : {args.latency} (dropping that many leading RTL samples)")

    aligned = rtl[args.latency:]
    n = min(len(aligned), len(golden))
    if n == 0:
        print("ERROR: nothing left to compare.")
        return 2

    mismatches = [i for i in range(n) if aligned[i] != golden[i]]
    print("-" * 52)
    if not mismatches:
        print(f"PASS: {n} samples match bit-for-bit, 0 differences.")
        if len(aligned) != len(golden):
            print(f"Note: lengths differ ({len(aligned)} vs {len(golden)}). "
                  f"Write {len(golden) + args.latency} samples in the testbench "
                  f"for an exact length match.")
        print("-" * 52)
        return 0

    first = mismatches[0]
    print(f"FAIL: {len(mismatches)} of {n} samples differ.")
    print(f"First mismatch at sample {first}: "
          f"golden = {golden[first]}, rtl = {aligned[first]}")
    print()
    print("  sample   golden      rtl")
    for i in mismatches[:10]:
        print(f"  {i:>6}   {golden[i]:>6}   {aligned[i]:>6}")
    print()
    print("Hints:")
    print("  - mismatch from sample 0        -> stimulus differs from the model")
    print("  - only the negative half wrong  -> missing $signed cast in am_envelope.v")
    print("  - correct then wrong midway     -> overflow, a signal is too narrow")
    print("  - off by a constant shift       -> wrong --latency value")
    print("-" * 52)
    return 1


if __name__ == "__main__":
    sys.exit(main())
