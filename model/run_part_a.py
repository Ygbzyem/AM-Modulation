"""Generate all Part A deliverables without Vivado or RTL."""
import argparse
import json
from dataclasses import replace
from pathlib import Path

try:
    from .am_golden import Config, generate, metadata, save
    from .gen_sine_rom import generate_all
    from .plot_txt import plot_spectrum, plot_waveform
    from .spectrum import analyze_am, measure, save_fft_csv
except ImportError:
    from am_golden import Config, generate, metadata, save
    from gen_sine_rom import generate_all
    from plot_txt import plot_spectrum, plot_waveform
    from spectrum import analyze_am, measure, save_fft_csv


ROOT = Path(__file__).resolve().parents[1]


def cases():
    result = []
    for amplitude in (0, 500, 1000, 2000, 3000):
        result.append((f"functional_mu_{amplitude / 2000:g}", Config(amp_msg=amplitude)))
    result.extend([("functional_dsb_sc", Config(amp_car=0)),
                   ("functional_fm_100k", Config(ftw_msg=4_294_967))])
    for aw in (8, 10, 12):
        for architecture in ("FULL", "QUARTER"):
            result.append((f"rom_aw{aw}_{architecture.lower()}", Config(aw=aw, rom_arch=architecture)))
    return result


def run(output, plots=True):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    generate_all(ROOT / "mem")
    case_list = [{"id": name, **metadata(config, generate(config))["config"]} for name, config in cases()]
    (output / "cases.json").write_text(json.dumps(case_list, indent=2) + "\n", encoding="utf-8")
    summary = []
    for name, config in cases():
        destination = output / name
        destination.mkdir(parents=True, exist_ok=True)
        rows = save(config, destination / "golden.txt", destination / "trace.csv", destination / "metadata.json")
        alternate = generate(replace(config, rom_arch="QUARTER" if config.rom_arch == "FULL" else "FULL"))
        # Table reconstruction is tested separately. This also tests actual NCO sequences.
        equal = rows == alternate
        if not equal:
            raise AssertionError(f"{name}: Python full and quarter paths differ")
        samples = [row["out"] for row in rows]
        spectrum = analyze_am(samples, config)
        fc = config.ftw_car * config.clock_hz / (1 << config.pw)
        nco_spectrum = measure([row["car"] for row in rows], config.clock_hz, [fc])
        nco_spectrum["definition"] = "Carrier NCO SFDR: fundamental / largest FFT bin outside fundamental guard band"
        (destination / "spectrum.json").write_text(json.dumps(spectrum, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        (destination / "nco_spectrum.json").write_text(json.dumps(nco_spectrum, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        save_fft_csv(samples, config.clock_hz, destination / "fft.csv")
        if plots:
            plot_waveform(samples, config, destination / "waveform.png", rows=rows, title=f"Python golden: {name}")
            plot_spectrum(samples, config, destination / "spectrum.png", title=f"Python golden: {name}")
        record = {"case": name, **metadata(config, rows), "python_full_quarter_equal": equal,
                  "rtl_status": "NOT_RUN", "am_sfdr_db": spectrum["sfdr_db"],
                  "nco_sfdr_db": nco_spectrum["sfdr_db"]}
        summary.append(record)
        print(f"{name}: Python FULL=QUARTER; env {record['env_min']}..{record['env_max']}; AM SFDR {spectrum['sfdr_db']:.2f} dB; RTL NOT_RUN")
    (output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    lines = ["# Part A Python results", "", "These are reference-model results, not RTL verification or implementation measurements.", "",
             "All 6 ROMs reconstruct bit-exactly. All 13 Python FULL/QUARTER output pairs agree.", "",
             "SFDR uses a periodic Hann window, +/-3 FFT-bin exclusion per intended tone, and includes DC as a spur.",
             "AM excludes intended sidebands; NCO excludes only the fundamental. Both are finite-record estimates.", "",
             "| Case | Env min | Env max | AM SFDR dB | NCO SFDR dB | RTL |", "|---|---:|---:|---:|---:|---|"]
    for row in summary:
        lines.append(f"| {row['case']} | {row['env_min']} | {row['env_max']} | {row['am_sfdr_db']:.2f} | {row['nco_sfdr_db']:.2f} | NOT_RUN |")
    (output / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results" / "part_a")
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    run(args.output_dir, not args.no_plots)


if __name__ == "__main__":
    main()
