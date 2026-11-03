"""Compare the Vivado simulation output against the Python golden model.

This file lives in golden_model/ and is run from the repository root:

    python golden_model/check_result.py                 # newest am_out.txt in the repo
    python golden_model/check_result.py path/to/am_out.txt

The file comes from tb/tb_am_top_filebased.v. Its header line holds the
configuration the RTL was simulated with, so the golden model is rebuilt with
exactly the same settings (a file without a header falls back to the defaults).

Every run is also saved to results/custom/<CASE>/ (rtl.txt, rtl_vs_golden.png,
rtl_vs_golden_spectrum.png, record.json) so golden_model/make_excel.py can put
it in results/results.xlsx. Use a different CASE in tb/am_config.txt for every
configuration you want to keep; the same CASE overwrites the earlier run.

Exit code: 0 = bit-exact match, 1 = mismatch, 2 = a file was missing.
"""

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # golden_model/
ROOT = HERE.parent                              # repository root
LATENCY = 3                                     # see header of src/am_modulator_top.v

# the reference model uses a relative import, so both paths must be importable
for entry in (str(HERE), str(ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

try:
    from am_golden import Config, generate
    from compare import read_header, read_samples
    from verify_rtl import config_from_header, evaluate_case
except ImportError:
    from golden_model.am_golden import Config, generate
    from golden_model.compare import read_header, read_samples
    from golden_model.verify_rtl import config_from_header, evaluate_case


def find_latest(name="am_out.txt"):
    hits = [p for p in ROOT.rglob(name) if ".git" not in p.parts]
    return max(hits, key=lambda p: p.stat().st_mtime) if hits else None


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("rtl_file", nargs="?", help="file written by tb_am_top_filebased")
    parser.add_argument("--latency", type=int,
                        help="leading RTL samples to drop (default: from header, else 3)")
    parser.add_argument("--no-save", action="store_true",
                        help="only compare, do not write results/custom/<CASE>/")
    args = parser.parse_args()

    rtl_path = Path(args.rtl_file) if args.rtl_file else find_latest()
    if rtl_path is not None and not rtl_path.is_absolute():
        rtl_path = Path.cwd() / rtl_path
    if rtl_path is None or not rtl_path.exists():
        print(f"ERROR: {rtl_path} not found. Run the simulation in Vivado first.")
        return 2

    lines = [l for l in rtl_path.read_text(encoding="utf-8-sig").splitlines()
             if l.strip() and not l.lstrip().startswith("#")]
    if any(ch in "xXzZ" for line in lines for ch in line):
        print(f"ERROR: {rtl_path} contains X or Z values.")
        print("       The sine ROM was not loaded: check the .mem paths in src/.")
        return 2

    header = read_header(rtl_path)
    config = config_from_header(header)
    if args.latency is None:
        args.latency = int(header.get("latency", LATENCY))
    rtl = read_samples(rtl_path)
    golden = [row["out"] for row in generate(config)]

    print(f"RTL file      : {rtl_path}")
    print(f"Config        : AW={config.aw} {config.rom_arch} ftw_car={config.ftw_car} "
          f"ftw_msg={config.ftw_msg} amp_car={config.amp_car} amp_msg={config.amp_msg}"
          + ("" if header else "  (no header, defaults)"))
    print(f"RTL samples   : {len(rtl)}")
    print(f"Golden samples: {len(golden)}")
    print(f"Latency       : {args.latency} (dropping that many leading RTL samples)")

    aligned = rtl[args.latency:]
    n = min(len(aligned), len(golden))
    if n == 0:
        print("ERROR: nothing left to compare.")
        return 2

    if not args.no_save:
        case = "".join(c if c.isalnum() or c in "._-" else "_" for c in header.get("case", "single")) or "single"
        case_dir = ROOT / "results" / "custom" / case
        evaluate_case(case, config, aligned, case_dir, source="custom", latency=args.latency)
        print(f"Saved to      : {case_dir.relative_to(ROOT)}  (python golden_model/make_excel.py)")

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
