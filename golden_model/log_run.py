"""Append one simulation run to a cumulative spreadsheet.

Every run becomes one row, so runs with different amplitudes or frequencies can
be compared side by side later. Nothing is overwritten: the workbook grows.

    python golden_model/log_run.py --label mu05
    python golden_model/log_run.py --label over_mod --amp-msg 3000
    python golden_model/log_run.py --label dsb_sc --amp-car 0 --amp-msg 2000
    python golden_model/log_run.py --label aw12_quarter --aw 12 --rom QUARTER

If results/run_info.txt exists (written by the testbench) its values are used as
defaults, so the stimulus can never disagree with what the RTL actually ran.
Explicit command-line options still win.

Reads : results/am_out.txt, optionally results/run_info.txt
Writes: results/am_runs.xlsx  (and results/am_runs.csv as a fallback)

Exit code: 0 = run logged and matched the model, 1 = logged but mismatched,
2 = a file was missing.
"""

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for entry in (str(HERE), str(ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

try:
    from am_golden import Config, generate
    from spectrum import analyze_am
except ImportError:
    from golden_model.am_golden import Config, generate
    from golden_model.spectrum import analyze_am

LATENCY = 3
COLUMNS = [
    "timestamp", "label", "aw", "rom",
    "ftw_car", "f_car_hz", "ftw_msg", "f_msg_hz",
    "amp_car", "amp_msg", "mu", "bandwidth_hz",
    "env_min", "env_max", "out_min", "out_max",
    "result", "mismatches", "n_compared",
    "carrier_ratio", "lower_ratio", "upper_ratio", "ideal_ratio", "sfdr_db",
    "rtl_file",
]


def read_run_info(path):
    """Parse the optional 'value LABEL' file written by the testbench."""
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].lstrip("-").isdigit():
            values[parts[1].upper()] = int(parts[0])
    return values


def append_xlsx(path, row):
    """Append one row, creating the workbook on first use."""
    try:
        from openpyxl import Workbook, load_workbook
        from openpyxl.styles import Font
    except ImportError:
        return False

    if path.exists():
        book = load_workbook(path)
        sheet = book["runs"] if "runs" in book.sheetnames else book.active
    else:
        book = Workbook()
        sheet = book.active
        sheet.title = "runs"
        sheet.append(COLUMNS)
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        sheet.freeze_panes = "A2"
        widths = {"A": 20, "B": 16, "D": 10, "E": 12, "F": 12, "G": 10, "H": 12, "Y": 40}
        for column, width in widths.items():
            sheet.column_dimensions[column].width = width

    sheet.append([row.get(name) for name in COLUMNS])
    book.save(path)
    return True


def append_csv(path, row):
    exists = path.exists()
    with open(path, "a", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rtl", default="results/am_out.txt")
    parser.add_argument("--workbook", default="results/am_runs.xlsx")
    parser.add_argument("--label", default="", help="short name for this run")
    parser.add_argument("--latency", type=int, default=LATENCY)
    parser.add_argument("--aw", type=int)
    parser.add_argument("--rom", choices=("FULL", "QUARTER"))
    parser.add_argument("--ftw-car", type=int)
    parser.add_argument("--ftw-msg", type=int)
    parser.add_argument("--amp-car", type=int)
    parser.add_argument("--amp-msg", type=int)
    parser.add_argument("--samples", type=int)
    args = parser.parse_args()

    rtl_path = Path(args.rtl)
    if not rtl_path.is_absolute():
        rtl_path = ROOT / rtl_path
    if not rtl_path.exists():
        print(f"ERROR: {rtl_path} not found. Run the simulation in Vivado first.")
        return 2

    info = read_run_info(rtl_path.parent / "run_info.txt")

    def pick(cli, key, fallback):
        if cli is not None:
            return cli
        return info.get(key, fallback)

    defaults = Config()
    config = Config(
        aw=pick(args.aw, "AW", defaults.aw),
        rom_arch=args.rom or ("QUARTER" if info.get("USE_QUARTER_ROM") else defaults.rom_arch),
        ftw_car=pick(args.ftw_car, "FTW_CAR", defaults.ftw_car),
        ftw_msg=pick(args.ftw_msg, "FTW_MSG", defaults.ftw_msg),
        amp_car=pick(args.amp_car, "AMP_CAR", defaults.amp_car),
        amp_msg=pick(args.amp_msg, "AMP_MSG", defaults.amp_msg),
        samples=pick(args.samples, "SAMPLES", defaults.samples),
    )

    raw = rtl_path.read_text(encoding="utf-8-sig").split()
    if any(ch in {"x", "X", "z", "Z"} for token in raw for ch in token):
        print(f"ERROR: {rtl_path} contains X or Z values. Check the .mem paths in src/.")
        return 2
    rtl = [int(token) for token in raw]

    rows = generate(config)
    golden = [row["out"] for row in rows]
    envelope = [row["env"] for row in rows]

    aligned = rtl[args.latency:]
    n = min(len(aligned), len(golden))
    mismatches = sum(1 for i in range(n) if aligned[i] != golden[i])
    passed = mismatches == 0 and n > 0

    # spectrum metrics, measured on the RTL stream itself
    carrier = lower = upper = ideal = sfdr = None
    try:
        analysis = analyze_am(aligned[:n], config)
        sfdr = analysis.get("sfdr_db")
        for line in analysis.get("lines", []):
            if line["label"] == "carrier":
                carrier = line["ratio_to_carrier"]
            elif line["label"] == "lower_sideband":
                lower = line["ratio_to_carrier"]
                ideal = line["ideal_ratio_to_carrier"]
            elif line["label"] == "upper_sideband":
                upper = line["ratio_to_carrier"]
    except Exception as error:                       # DSB-SC and edge cases
        print(f"Note: spectrum metrics skipped ({error})")

    clock = config.clock_hz
    scale = clock / (1 << config.pw)
    row = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "label": args.label or "run",
        "aw": config.aw,
        "rom": config.rom_arch,
        "ftw_car": config.ftw_car,
        "f_car_hz": round(config.ftw_car * scale, 2),
        "ftw_msg": config.ftw_msg,
        "f_msg_hz": round(config.ftw_msg * scale, 2),
        "amp_car": config.amp_car,
        "amp_msg": config.amp_msg,
        "mu": round(config.amp_msg / config.amp_car, 4) if config.amp_car else None,
        "bandwidth_hz": round(2 * config.ftw_msg * scale, 2),
        "env_min": min(envelope),
        "env_max": max(envelope),
        "out_min": min(aligned[:n]) if n else None,
        "out_max": max(aligned[:n]) if n else None,
        "result": "PASS" if passed else "FAIL",
        "mismatches": mismatches,
        "n_compared": n,
        "carrier_ratio": round(carrier, 4) if carrier is not None else None,
        "lower_ratio": round(lower, 4) if lower is not None else None,
        "upper_ratio": round(upper, 4) if upper is not None else None,
        "ideal_ratio": round(ideal, 4) if ideal is not None else None,
        "sfdr_db": round(sfdr, 2) if sfdr is not None else None,
        "rtl_file": str(rtl_path),
    }

    workbook_path = Path(args.workbook)
    if not workbook_path.is_absolute():
        workbook_path = ROOT / workbook_path
    workbook_path.parent.mkdir(parents=True, exist_ok=True)

    if append_xlsx(workbook_path, row):
        target = workbook_path
    else:
        target = workbook_path.with_suffix(".csv")
        print("Note: openpyxl not installed, writing CSV instead (pip install openpyxl)")
    append_csv(workbook_path.with_suffix(".csv"), row)

    print("=" * 62)
    print(f" Logged run '{row['label']}'")
    print(f"   AW={row['aw']} ROM={row['rom']}  "
          f"f_car={row['f_car_hz'] / 1e3:.1f} kHz  f_msg={row['f_msg_hz'] / 1e3:.1f} kHz")
    print(f"   amp_car={row['amp_car']} amp_msg={row['amp_msg']} mu={row['mu']}")
    print(f"   envelope {row['env_min']} .. {row['env_max']}   "
          f"output {row['out_min']} .. {row['out_max']}")
    if row["sfdr_db"] is not None:
        print(f"   sideband ratio {row['lower_ratio']} / {row['upper_ratio']} "
              f"(ideal {row['ideal_ratio']})   SFDR {row['sfdr_db']} dB")
    print(f"   {row['result']}: {row['mismatches']} mismatches over {row['n_compared']} samples")
    print(f" Workbook: {target}")
    print("=" * 62)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
