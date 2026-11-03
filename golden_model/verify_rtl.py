"""Compare RTL simulation output with the Python golden model, case by case.

Run tb/tb_am_regression.v in Vivado first; it writes rtl_case01.txt ...
rtl_case18.txt into the simulator run directory. Then, from the repository root:

    python golden_model/verify_rtl.py                  # find the files automatically
    python golden_model/verify_rtl.py --rtl-dir PATH   # or point at the folder
    python golden_model/verify_rtl.py --no-plots       # comparison only

For every case it writes into results/rtl/<case>/:
    rtl.txt                      the RTL samples, warm-up samples removed
    rtl_vs_golden.png            golden waveform | RTL waveform, and RTL - golden below
    rtl_vs_golden_spectrum.png   golden spectrum | RTL spectrum
    record.json                  configuration, comparison result and measurements
and a summary table in results/rtl/RTL_VERIFICATION.md and rtl_verification.json.

Exit code: 0 = every case bit-exact, 1 = at least one mismatch, 2 = files missing.
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for entry in (str(HERE), str(ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

try:
    from am_golden import Config, generate
    from compare import read_header, read_samples
    from spectrum import analyze_am, fft_amplitude
except ImportError:
    from golden_model.am_golden import Config, generate
    from golden_model.compare import read_header, read_samples
    from golden_model.spectrum import analyze_am, fft_amplitude

DEFAULT_FTW_CAR = 42_949_673
DEFAULT_FTW_MSG = 858_993

# index -> (case name, golden configuration). Must match tb/tb_am_regression.v;
# the header line of every RTL file is checked against this table.
CASES = {
    1: ("functional_mu_0", Config(amp_msg=0)),
    2: ("functional_mu_0.25", Config(amp_msg=500)),
    3: ("functional_mu_0.5", Config(amp_msg=1000)),
    4: ("functional_mu_1", Config(amp_msg=2000)),
    5: ("functional_mu_1.5", Config(amp_msg=3000)),
    6: ("functional_dsb_sc", Config(amp_car=0)),
    7: ("functional_fm_100k", Config(ftw_msg=4_294_967)),
    8: ("rom_aw8_full", Config(aw=8, rom_arch="FULL")),
    9: ("rom_aw8_quarter", Config(aw=8, rom_arch="QUARTER")),
    10: ("rom_aw10_full", Config(aw=10, rom_arch="FULL")),
    11: ("rom_aw10_quarter", Config(aw=10, rom_arch="QUARTER")),
    12: ("rom_aw12_full", Config(aw=12, rom_arch="FULL")),
    13: ("rom_aw12_quarter", Config(aw=12, rom_arch="QUARTER")),
    14: ("edge_amp_max", Config(amp_car=4095, amp_msg=4095)),
    15: ("edge_dsb_max", Config(amp_car=0, amp_msg=4095)),
    16: ("edge_ftw_nyquist", Config(ftw_car=1 << 31)),
    17: ("edge_ftw_max", Config(ftw_car=(1 << 32) - 1)),
    18: ("edge_ftw_zero", Config(ftw_car=0)),
}


def find_rtl_dir(pattern="rtl_case01.txt"):
    """Newest folder under the repository that holds `pattern`."""
    hits = [p for p in ROOT.rglob(pattern) if ".git" not in p.parts]
    if not hits:
        return None
    return max(hits, key=lambda p: p.stat().st_mtime).parent


def config_from_header(header, base=None):
    """Build a golden Config from an RTL header; fall back to `base` or defaults."""
    base = base or Config()
    if not header:
        return base
    return Config(aw=int(header.get("aw", base.aw)),
                  rom_arch=header.get("rom", base.rom_arch).upper(),
                  ftw_car=int(header.get("ftw_car", base.ftw_car)),
                  ftw_msg=int(header.get("ftw_msg", base.ftw_msg)),
                  amp_car=int(header.get("amp_car", base.amp_car)),
                  amp_msg=int(header.get("amp_msg", base.amp_msg)),
                  samples=int(header.get("samples", base.samples)))


def compare_streams(golden, rtl):
    n = min(len(golden), len(rtl))
    diffs = [i for i in range(n) if golden[i] != rtl[i]]
    return {
        "n_golden": len(golden),
        "n_rtl": len(rtl),
        "n_compared": n,
        "mismatches": len(diffs),
        "max_abs_error": max((abs(golden[i] - rtl[i]) for i in diffs), default=0),
        "first_mismatch": None if not diffs else
            {"index": diffs[0], "golden": golden[diffs[0]], "rtl": rtl[diffs[0]]},
        "passed": not diffs and len(golden) == len(rtl),
    }


def plot_side_by_side(name, config, golden, rtl, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    golden = np.asarray(golden)
    rtl = np.asarray(rtl)
    t_us = np.arange(len(golden)) / config.clock_hz * 1e6
    peak = max(int(np.max(np.abs(golden))), int(np.max(np.abs(rtl))), 1)
    ylim = (-1.1 * peak, 1.1 * peak)

    fig = plt.figure(figsize=(14, 7.2))
    grid = fig.add_gridspec(2, 2, height_ratios=[3, 1.3])
    ax_g = fig.add_subplot(grid[0, 0])
    ax_r = fig.add_subplot(grid[0, 1], sharey=ax_g)
    ax_e = fig.add_subplot(grid[1, :])

    ax_g.plot(t_us, golden, color="#2463a6", linewidth=0.5)
    ax_g.set(title="Python golden model", xlabel="Time (us)", ylabel="am_out (signed LSB)", ylim=ylim)
    ax_r.plot(t_us, rtl, color="#2a9259", linewidth=0.5)
    ax_r.set(title="RTL simulation (tb_am_regression)", xlabel="Time (us)")
    error = rtl - golden
    ax_e.plot(t_us, error, color="#c74b28", linewidth=0.8)
    span = max(1, int(np.max(np.abs(error))))
    ax_e.set(title=f"RTL - golden: {int(np.count_nonzero(error))} mismatches in {len(error)} samples",
             xlabel="Time (us)", ylabel="Error (LSB)", ylim=(-1.5 * span, 1.5 * span))
    for axis in (ax_g, ax_r, ax_e):
        axis.grid(alpha=0.25)

    fc = config.ftw_car * config.clock_hz / (1 << config.pw)
    fm = config.ftw_msg * config.clock_hz / (1 << config.pw)
    fig.suptitle(f"{name}   AW={config.aw} {config.rom_arch}   fc={fc / 1e6:.3f} MHz   "
                 f"fm={fm / 1e3:.2f} kHz   amp_car={config.amp_car}   amp_msg={config.amp_msg}",
                 fontsize=11)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)


def plot_spectrum_side_by_side(name, config, golden, rtl, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    fc = config.ftw_car * config.clock_hz / (1 << config.pw)
    fm = config.ftw_msg * config.clock_hz / (1 << config.pw)
    fc = fc % config.clock_hz                       # fold aliases (FTW near 2^32) into 0 .. fs/2
    if fc > config.clock_hz / 2:
        fc = config.clock_hz - fc
    span = max(4 * fm, 100e3)
    zoom = (max(0.0, fc - span) / 1e6, min(config.clock_hz / 2, fc + span) / 1e6)
    if zoom[1] - zoom[0] < 2 * config.clock_hz / len(golden) / 1e6:
        zoom = (0.0, config.clock_hz / 2e6)

    fig, axes = plt.subplots(2, 2, figsize=(14, 7.2), sharey="row")
    for column, (samples, label, color) in enumerate(((golden, "Python golden model", "#2463a6"),
                                                      (rtl, "RTL simulation", "#2a9259"))):
        freqs, amps = fft_amplitude(np.asarray(samples, dtype=float), config.clock_hz)
        ref = max(float(np.max(amps)), 1e-30)
        db = 20 * np.log10(np.maximum(amps / ref, 1e-7))
        top, bottom = axes[0, column], axes[1, column]
        top.plot(freqs / 1e6, db, color=color, linewidth=0.7)
        top.set(title=f"{label}: full band", xlabel="Frequency (MHz)", xlim=(0, config.clock_hz / 2e6), ylim=(-120, 5))
        visible = (freqs / 1e6 >= zoom[0]) & (freqs / 1e6 <= zoom[1])
        marker, stems, base = bottom.stem(freqs[visible] / 1e6, db[visible], bottom=-120)
        plt.setp(marker, markersize=3, color=color)
        plt.setp(stems, linewidth=1, color=color)
        base.set_visible(False)
        bottom.set(title=f"{label}: carrier and sidebands", xlabel="Frequency (MHz)", xlim=zoom, ylim=(-120, 10))
        for axis in (top, bottom):
            axis.grid(alpha=0.25)
    axes[0, 0].set_ylabel("dB re largest bin")
    axes[1, 0].set_ylabel("dB re largest bin")
    fig.suptitle(f"{name}   spectrum, periodic Hann window, {len(golden)} samples", fontsize=11)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=110)
    plt.close(fig)


def evaluate_case(name, config, rtl, case_dir, plots=True, source="regression", index=None, latency=3):
    """Compare one RTL stream with the golden model, save files, return a record."""
    rows = generate(config)
    golden = [row["out"] for row in rows]
    result = compare_streams(golden, rtl)
    status = "PASS" if result["passed"] else "FAIL"
    try:
        sfdr = analyze_am(rtl, config)["sfdr_db"] if len(rtl) == len(golden) else None
    except Exception:                      # degenerate tones (fc = 0, Nyquist)
        sfdr = None

    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "rtl.txt").write_text("".join(f"{v}\n" for v in rtl), encoding="ascii")
    figures = {}
    if plots and len(rtl) == len(golden):
        for key, filename, draw in (("waveform", "rtl_vs_golden.png", plot_side_by_side),
                                    ("spectrum", "rtl_vs_golden_spectrum.png", plot_spectrum_side_by_side)):
            try:
                draw(name, config, golden, rtl, case_dir / filename)
                figures[key] = filename
            except Exception as error:      # a figure must never hide the comparison result
                print(f"       WARNING: {filename} not drawn for {name}: {error}")

    record = {"index": index, "case": name, "source": source,
              "aw": config.aw, "rom": config.rom_arch, "clock_hz": config.clock_hz,
              "ftw_car": config.ftw_car, "ftw_msg": config.ftw_msg,
              "amp_car": config.amp_car, "amp_msg": config.amp_msg, "samples": config.samples,
              "latency_dropped": latency, "status": status,
              "env_min": min(r["env"] for r in rows), "env_max": max(r["env"] for r in rows),
              "golden_out_min": min(golden), "golden_out_max": max(golden),
              "rtl_out_min": min(rtl) if rtl else None, "rtl_out_max": max(rtl) if rtl else None,
              "sfdr_db": sfdr, "figures": figures, **result}
    (case_dir / "record.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def write_summary(records, out_dir):
    (out_dir / "rtl_verification.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    lines = ["# RTL verification against the Python golden model", "",
             "Generated by `golden_model/verify_rtl.py` from the output of `tb/tb_am_regression.v`.",
             "Each RTL stream drops its first 3 samples (pipeline warm-up) and is compared",
             "sample by sample with the golden model, no offset search.", "",
             "| # | Case | AW | ROM | amp_car | amp_msg | Samples | Mismatches | Result |",
             "|---:|---|---:|---|---:|---:|---:|---:|---|"]
    for r in records:
        lines.append(f"| {r['index']} | {r['case']} | {r['aw']} | {r['rom']} | {r['amp_car']} | "
                     f"{r['amp_msg']} | {r['n_compared']} | {r['mismatches']} | {r['status']} |")
    passed = sum(r["status"] == "PASS" for r in records)
    lines += ["", f"**{passed} / {len(records)} cases bit-exact.**", ""]
    (out_dir / "RTL_VERIFICATION.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rtl-dir", type=Path, help="folder holding rtl_caseNN.txt")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "results" / "rtl")
    parser.add_argument("--latency", type=int, default=3)
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()

    rtl_dir = args.rtl_dir or find_rtl_dir()
    if rtl_dir is None or not rtl_dir.exists():
        print("ERROR: no rtl_case01.txt found. Run tb_am_regression in Vivado first,")
        print("       or pass --rtl-dir <folder>.")
        return 2
    print(f"RTL folder: {rtl_dir}\n")
    print(f"{'#':>3}  {'case':<20} {'samples':>8} {'mismatch':>9}  result")

    records, missing = [], 0
    for index, (name, expected_config) in CASES.items():
        path = rtl_dir / f"rtl_case{index:02d}.txt"
        if not path.exists():
            print(f"{index:>3}  {name:<20} {'-':>8} {'-':>9}  MISSING")
            missing += 1
            continue
        header = read_header(path)
        config = config_from_header(header, expected_config)
        if config != expected_config or header.get("case", name) != name:
            print(f"{index:>3}  {name:<20} header does not match CASES, testbench and script out of sync")
            return 2
        latency = int(header.get("latency", args.latency))
        rtl = read_samples(path)[latency:]
        record = evaluate_case(name, config, rtl, args.out_dir / name, plots=not args.no_plots,
                               source="regression", index=index, latency=latency)
        print(f"{index:>3}  {name:<20} {record['n_compared']:>8} {record['mismatches']:>9}  {record['status']}")
        if record["first_mismatch"]:
            fm = record["first_mismatch"]
            print(f"       first mismatch at {fm['index']}: golden={fm['golden']} rtl={fm['rtl']}")
        records.append(record)

    write_summary(records, args.out_dir)
    failed = sum(r["status"] != "PASS" for r in records)
    print(f"\n{len(records) - failed}/{len(CASES)} PASS, {failed} FAIL, {missing} missing")
    print(f"Summary: {args.out_dir / 'RTL_VERIFICATION.md'}")
    print("Excel  : python golden_model/make_excel.py")
    if missing:
        return 2
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
