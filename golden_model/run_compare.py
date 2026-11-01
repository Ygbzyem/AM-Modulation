r"""Step 2 of the Vivado flow: build the golden model and compare it to the RTL.

Run this after pressing Run Simulation in Vivado. No arguments are needed: the
script reads the very same work/config.txt that the testbench read, so the two
sides can never drift apart.

    python golden_model/run_compare.py
    python golden_model/run_compare.py --work "C:/AM Modulation/work"

Reads:  work/config.txt        stimulus (edited by the user)
        work/rtl/*.txt         six result files written by Vivado
Writes: work/golden/*.txt      six reference files computed in Python
        work/compare/report.txt    human-readable report
        work/compare/summary.csv   table for Excel

Exit code: 0 = every configuration passed, 1 = a mismatch, 2 = missing files.
"""

import argparse
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from am_golden import Config, generate          # noqa: E402
from gen_sine_rom import generate_all           # noqa: E402

LATENCY = 3                                     # 2 ROM stages + 1 multiplier stage
CONFIGURATIONS = [(8, "FULL"), (8, "QUARTER"),
                  (10, "FULL"), (10, "QUARTER"),
                  (12, "FULL"), (12, "QUARTER")]
REQUIRED = ("FTW_CAR", "FTW_MSG", "AMP_CAR", "AMP_MSG", "SAMPLES")


def read_config(path):
    """Parse 'value LABEL' lines into a dictionary."""
    values = {}
    for number, line in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2 or not parts[0].lstrip("-").isdigit():
            raise ValueError(f"{path}: line {number} is not of the form 'value LABEL'")
        values[parts[1].upper()] = int(parts[0])
    missing = set(REQUIRED) - set(values)
    if missing:
        raise ValueError(f"{path}: missing {', '.join(sorted(missing))}")
    return values


def read_samples(path):
    return [int(x) for x in Path(path).read_text(encoding="utf-8-sig").split()]


def compare_streams(golden, rtl):
    """Drop LATENCY leading RTL samples, then compare sample by sample."""
    aligned = rtl[LATENCY:]
    n = min(len(golden), len(aligned))
    mismatches = [i for i in range(n) if golden[i] != aligned[i]]
    return {
        "n_compared": n,
        "mismatches": len(mismatches),
        "first_mismatch": mismatches[0] if mismatches else None,
        "golden_value": golden[mismatches[0]] if mismatches else None,
        "rtl_value": aligned[mismatches[0]] if mismatches else None,
        "passed": not mismatches and n > 0 and len(golden) == n,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--work", default=str(ROOT / "work"),
                        help="folder holding config.txt, rtl/, golden/ and compare/")
    args = parser.parse_args()

    work = Path(args.work).resolve()
    rtl_dir, golden_dir, compare_dir = work / "rtl", work / "golden", work / "compare"
    for folder in (golden_dir, compare_dir):
        folder.mkdir(parents=True, exist_ok=True)

    if not (work / "config.txt").exists():
        print(f"config.txt not found in {work}")
        return 2

    cfg = read_config(work / "config.txt")
    print("=" * 62)
    print(" Stimulus read from config.txt")
    for name in REQUIRED:
        print(f"   {name:<10}= {cfg[name]}")
    if cfg["AMP_CAR"]:
        print(f"   {'mu':<10}= {cfg['AMP_MSG'] / cfg['AMP_CAR']:.3f}")
    else:
        print(f"   {'mu':<10}= DSB-SC (amp_car = 0)")
    print("=" * 62)

    generate_all(work / "mem")              # make sure the .mem tables exist and are correct

    results = []
    missing_rtl = False

    for aw, arch in CONFIGURATIONS:
        name = f"AW{aw}_{arch}"
        rtl_file = rtl_dir / f"am_out_{name}.txt"
        golden_file = golden_dir / f"golden_{name}.txt"

        config = Config(aw=aw, rom_arch=arch,
                        ftw_car=cfg["FTW_CAR"], ftw_msg=cfg["FTW_MSG"],
                        amp_car=cfg["AMP_CAR"], amp_msg=cfg["AMP_MSG"],
                        samples=cfg["SAMPLES"])
        rows = generate(config)
        golden = [r["out"] for r in rows]
        golden_file.write_text("\n".join(map(str, golden)) + "\n", encoding="ascii")

        envelope = [r["env"] for r in rows]
        record = {"configuration": name, "aw": aw, "rom": arch,
                  "env_min": min(envelope), "env_max": max(envelope),
                  "out_min": min(golden), "out_max": max(golden)}

        if not rtl_file.exists():
            missing_rtl = True
            record.update(result="MISSING RTL FILE", n_compared=0, mismatches="-")
            results.append(record)
            continue

        outcome = compare_streams(golden, read_samples(rtl_file))
        record.update(result="PASS" if outcome["passed"] else "FAIL",
                      n_compared=outcome["n_compared"],
                      mismatches=outcome["mismatches"],
                      first_mismatch=outcome["first_mismatch"],
                      golden_value=outcome["golden_value"],
                      rtl_value=outcome["rtl_value"])
        results.append(record)

    # ---------------- text report ----------------
    lines = ["RTL vs GOLDEN MODEL COMPARISON REPORT", "=" * 62]
    for name in REQUIRED:
        lines.append(f"{name:<10}= {cfg[name]}")
    lines += [f"Pipeline latency skipped: {LATENCY} samples", "",
              f"{'configuration':<16}{'result':<18}{'samples':>10}{'diff':>8}",
              "-" * 62]
    for r in results:
        lines.append(f"{r['configuration']:<16}{r['result']:<18}"
                     f"{r['n_compared']:>10}{str(r['mismatches']):>8}")
        if r["result"] == "FAIL":
            lines.append(f"    first mismatch at sample {r['first_mismatch']}: "
                         f"golden = {r['golden_value']}, rtl = {r['rtl_value']}")
    lines.append("-" * 62)

    # extra check: both ROM architectures must produce identical samples
    lines += ["", "Cross-check: are FULL and QUARTER identical?"]
    for aw in (8, 10, 12):
        full = rtl_dir / f"am_out_AW{aw}_FULL.txt"
        quarter = rtl_dir / f"am_out_AW{aw}_QUARTER.txt"
        if full.exists() and quarter.exists():
            identical = read_samples(full) == read_samples(quarter)
            lines.append(f"   AW={aw:<3} {'IDENTICAL' if identical else 'DIFFERENT'}")

    all_passed = all(r["result"] == "PASS" for r in results)
    lines += ["", "CONCLUSION: ALL CONFIGURATIONS PASS" if all_passed
              else "CONCLUSION: SOME CONFIGURATIONS DID NOT PASS"]

    report = "\n".join(lines)
    (compare_dir / "report.txt").write_text(report + "\n", encoding="utf-8")
    print(report)

    # ---------------- CSV for Excel ----------------
    with open(compare_dir / "summary.csv", "w", newline="", encoding="utf-8-sig") as fp:
        columns = ["configuration", "aw", "rom", "result", "n_compared", "mismatches",
                   "env_min", "env_max", "out_min", "out_max"]
        writer = csv.DictWriter(fp, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for record in results:
            writer.writerow(record)

    print(f"\nReport: {compare_dir / 'report.txt'}")
    print(f"Table : {compare_dir / 'summary.csv'}")

    if missing_rtl:
        print("\nSome RTL result files are missing. Run the simulation in Vivado first.")
        return 2
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
