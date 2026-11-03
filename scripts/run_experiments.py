#!/usr/bin/env python3
"""Run all configurations in scripts/cases.yaml and write results/results.xlsx.

    python scripts/run_experiments.py [--impl] [--cases ID ...] [--skip-sim] [--vivado-bin DIR]
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

from model.am_golden import Config, metadata, save                    # noqa: E402
from model.compare import compare, read_samples                       # noqa: E402
from model.plot_txt import plot_spectrum, plot_waveform               # noqa: E402
from model.spectrum import analyze_am                                 # noqa: E402
import vivado_reports as vr                                           # noqa: E402

TOP = "am_modulator_top"
WORK = ROOT / "results" / "work"
RPT = ROOT / "results" / "rpt"
FIG = ROOT / "results" / "figures"
SRC = ROOT / "src"
MEM = ROOT / "mem"
TB = ROOT / "tb" / "tb_am_modulator.v"
RESOURCE_KEYS = ("lut", "ff", "lutram", "bram", "dsp", "wns", "fmax_mhz", "power_dynamic_w", "power_total_w")


def load_cases(path, selected=None):
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    cases = [{**data["defaults"], **raw} for raw in data["cases"]]
    for case in cases:
        case["rom_arch"] = str(case["rom_arch"]).upper()
    ids = [c["id"] for c in cases]
    if len(set(ids)) != len(ids):
        sys.exit("cases.yaml: duplicate case id")
    if selected:
        unknown = set(selected) - set(ids)
        if unknown:
            sys.exit(f"Unknown case(s): {sorted(unknown)}")
        cases = [c for c in cases if c["id"] in selected]
    return cases


def case_config(case):
    return Config(clock_hz=case["clock_hz"], aw=case["aw"], rom_arch=case["rom_arch"],
                  ftw_car=case["ftw_car"], ftw_msg=case["ftw_msg"],
                  amp_car=case["amp_car"], amp_msg=case["amp_msg"], samples=case["samples"])


def find_tool(name, bin_dir=None):
    found = shutil.which(name, path=str(bin_dir)) if bin_dir else None
    found = found or shutil.which(name)
    if not found:
        sys.exit(f"'{name}' not found in PATH (use --vivado-bin)")
    return found


def run(cmd, cwd, log_path):
    with open(log_path, "w", encoding="utf-8", errors="ignore") as log:
        return subprocess.run([str(c) for c in cmd], cwd=cwd, stdout=log,
                              stderr=subprocess.STDOUT).returncode


def rtl_files():
    files = [p for p in sorted(SRC.rglob("*.v"))
             if not p.name.lower().startswith(("tb_", "testbench")) and not p.name.lower().endswith("_tb.v")]
    if not files:
        sys.exit(f"No .v files under {SRC}")
    return files


def mem_file(aw, arch):
    path = MEM / f"sine_{arch}_AW{aw}.mem"
    if not path.exists():
        sys.exit(f"Missing {path}")
    return path


def make_testbench(case, work):
    """Copy of tb/tb_am_modulator.v with this case's structural parameters and length."""
    text = TB.read_text(encoding="utf-8")
    instance = re.compile(r"\b\w+\s+(?:#\s*\((?:[^()]|\([^()]*\))*\)\s*)?u_dut\s*\(")
    override = (f'{TOP} #(.AW({case["aw"]}), .USE_QUARTER_ROM({int(case["rom_arch"] == "QUARTER")}), '
                f'.FULL_MEM_FILE("rom_full.mem"), .QUARTER_MEM_FILE("rom_quarter.mem")) u_dut (')
    text, n_instance = instance.subn(override, text, count=1)
    text, n_loop = re.subn(r"i\s*<\s*10000\b", f"i < {case['samples'] + case['latency']}", text, count=1)
    if n_instance != 1 or n_loop != 1:
        sys.exit(f"{TB}: cannot locate the u_dut instance or the 10000-sample loop")
    out = work / "tb_case.v"
    out.write_text(text, encoding="utf-8")
    return out


def simulate(case, work, bin_dir):
    shutil.copy(mem_file(case["aw"], "full"), work / "rom_full.mem")
    shutil.copy(mem_file(case["aw"], "quarter"), work / "rom_quarter.mem")
    tb = make_testbench(case, work)
    xvlog, xelab, xsim = (find_tool(t, bin_dir) for t in ("xvlog", "xelab", "xsim"))
    steps = [
        ("xvlog", [xvlog, *rtl_files(), tb]),
        ("xelab", [xelab, "-debug", "typical", "work.tb_am_modulator", "-s", "snap"]),
        ("xsim", [xsim, "snap", "-tclbatch", ROOT / "scripts" / "run_sim.tcl",
                  "-testplusarg", f"FTW_CAR={case['ftw_car']}", "-testplusarg", f"FTW_MSG={case['ftw_msg']}",
                  "-testplusarg", f"AMP_CAR={case['amp_car']}", "-testplusarg", f"AMP_MSG={case['amp_msg']}",
                  "-testplusarg", "OUTFILE=am_out.txt"]),
    ]
    (work / "am_out.txt").unlink(missing_ok=True)
    for name, cmd in steps:
        if run(cmd, work, work / f"{name}.log") != 0:
            sys.exit(f"{case['id']}: {name} failed, see {work / (name + '.log')}")
    if "ERROR" in (work / "xsim.log").read_text(errors="ignore"):
        sys.exit(f"{case['id']}: testbench reported ERROR, see {work / 'xsim.log'}")
    return work / "am_out.txt"


def run_case(case, args):
    work = WORK / case["id"]
    work.mkdir(parents=True, exist_ok=True)
    config = case_config(case)
    rows = save(config, work / "golden.txt", work / "trace.csv", work / "metadata.json")
    meta = metadata(config, rows)
    golden = [r["out"] for r in rows]

    rtl_path = work / "am_out.txt" if args.skip_sim else simulate(case, work, args.vivado_bin)
    if not rtl_path.exists():
        sys.exit(f"{case['id']}: {rtl_path} not found")

    latency = case["latency"]
    result = compare(work / "golden.txt", rtl_path, skip_rtl=latency, expected_samples=case["samples"])
    passed = result["passed"]
    if not passed:
        (work / "diagnostic.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    try:
        rtl = read_samples(rtl_path)[latency:]
    except ValueError:
        rtl = None

    spectrum = sfdr = None
    figures = {"waveform": None, "spectrum": None}
    if rtl is not None and len(rtl) == len(golden):
        FIG.mkdir(parents=True, exist_ok=True)
        spectrum = analyze_am(rtl, config)
        sfdr = spectrum["sfdr_db"]
        wave, spec = FIG / f"{case['id']}_waveform.png", FIG / f"{case['id']}_spectrum.png"
        plot_waveform(golden, config, wave, rows, rtl, title=f"{case['id']}: {result['status']}")
        plot_spectrum(rtl, config, spec, title=f"RTL spectrum: {case['id']}")
        figures = {"waveform": wave.relative_to(ROOT).as_posix(), "spectrum": spec.relative_to(ROOT).as_posix()}

    lines = [{**line, "freq_error_hz": line["measured_bin_hz"] - line["expected_hz"]}
             for line in (spectrum or {}).get("lines", [])]
    first = result["first_mismatch"]
    return {
        "case_id": case["id"], "group": case["group"], "note": case.get("note", ""),
        "aw": case["aw"], "rom_arch": case["rom_arch"],
        "ftw_car": case["ftw_car"], "ftw_msg": case["ftw_msg"],
        "amp_car": case["amp_car"], "amp_msg": case["amp_msg"], "mu": meta["mu"],
        "f_car_hz": meta["fc_hz"], "f_msg_hz": meta["fm_hz"],
        "bandwidth_hz": 2 * meta["fm_hz"] if case["amp_msg"] else 0.0,
        "env_min": meta["env_min"], "env_max": meta["env_max"],
        "out_min": min(rtl) if rtl else None, "out_max": max(rtl) if rtl else None,
        "result": result["status"], "mismatch_count": result["mismatches"],
        "first_mismatch": first["index"] if first else None, "max_abs_error": result["max_abs_error"],
        "error": result["error"], "latency": latency, "sfdr_db": sfdr,
        "impl_tag": case["impl_tag"], "figures": figures, "spectrum": lines,
    }


def run_impl(cases, bin_dir):
    vivado = find_tool("vivado", bin_dir)
    impl_work = WORK / "impl"
    impl_work.mkdir(parents=True, exist_ok=True)
    for aw, arch in sorted({(c["aw"], c["rom_arch"]) for c in cases if c["group"] == "resource"}):
        tag = f"AW{aw}_{arch}"
        print(f"[impl] {tag}")
        cmd = [vivado, "-mode", "batch", "-nojournal", "-log", impl_work / f"{tag}.log",
               "-source", ROOT / "scripts" / "sweep_impl.tcl", "-tclargs", aw, arch]
        if subprocess.run([str(c) for c in cmd], cwd=impl_work).returncode != 0:
            sys.exit(f"Vivado failed for {tag}, see {impl_work / (tag + '.log')}")


def attach_resources(rows):
    cache, missing = {}, set()
    for row in rows:
        tag = row["impl_tag"]
        if tag not in cache:
            try:
                cache[tag] = vr.parse_impl_dir(RPT / tag)
            except (OSError, ValueError) as exc:
                print(f"[warning] {tag}: {exc}")
                cache[tag] = None
                missing.add(tag)
        row["rpt_dir"] = f"results/rpt/{tag}"
        for key in RESOURCE_KEYS:
            row[key] = None if cache[tag] is None else cache[tag][key]
    return missing


def check_rom_difference(rows):
    by_key = {(r["aw"], r["rom_arch"]): r for r in rows if r["group"] == "resource"}
    for aw in (8, 10, 12):
        full, quarter = by_key.get((aw, "FULL")), by_key.get((aw, "QUARTER"))
        if full and quarter and full["lut"] is not None and quarter["lut"] is not None:
            if all(full[k] == quarter[k] for k in ("lut", "ff", "lutram", "bram", "dsp")):
                print(f"[warning] AW={aw}: FULL and QUARTER report identical resources")


def write_verification_csv(rows, path):
    cols = ["case_id", "AW", "ROM_ARCH", "ftw_car", "ftw_msg", "amp_car", "amp_msg", "mu", "env_min",
            "env_max", "out_min", "out_max", "result", "mismatch_count", "latency"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(cols)
        for r in rows:
            writer.writerow([r["case_id"], r["aw"], r["rom_arch"], r["ftw_car"], r["ftw_msg"], r["amp_car"],
                             r["amp_msg"], "" if r["mu"] is None else r["mu"], r["env_min"], r["env_max"],
                             r["out_min"], r["out_max"], r["result"], r["mismatch_count"], r["latency"]])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cases-file", default=ROOT / "scripts" / "cases.yaml")
    ap.add_argument("--cases", nargs="*")
    ap.add_argument("--impl", action="store_true")
    ap.add_argument("--skip-sim", action="store_true")
    ap.add_argument("--vivado-bin")
    ap.add_argument("--out", default=ROOT / "results" / "results.xlsx")
    args = ap.parse_args()

    cases = load_cases(args.cases_file, args.cases)
    if args.impl:
        run_impl(cases, args.vivado_bin)

    rows = []
    for case in cases:
        row = run_case(case, args)
        print(f"{row['case_id']}: {row['result']}")
        rows.append(row)

    missing = attach_resources(rows)
    check_rom_difference(rows)

    results_dir = ROOT / "results"
    results_dir.mkdir(exist_ok=True)
    (results_dir / "summary.json").write_text(json.dumps(rows, indent=1, default=float), encoding="utf-8")
    write_verification_csv(rows, results_dir / "verification_run.csv")

    import write_excel
    write_excel.build(rows, Path(args.out), ROOT)

    print(f"{sum(r['result'] == 'PASS' for r in rows)}/{len(rows)} PASS -> {args.out}")
    for tag in sorted(missing):
        print(f"missing reports: results/rpt/{tag}")
    return 0 if all(r["result"] == "PASS" for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
