#!/usr/bin/env python3
"""Generate the report figures (docs/figures) and LaTeX tables (docs/report/tables) from results/summary.json.

    python scripts/make_report_assets.py

Needs results/summary.json and results/work/<case>/{am_out.txt,trace.csv}, both written by run_experiments.py.
Resource columns stay "--" until results/rpt/ holds the Vivado reports and run_experiments.py has been re-run.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from model.am_golden import Config                      # noqa: E402
from model.compare import read_samples                  # noqa: E402
from model.spectrum import analyze_am, fft_amplitude    # noqa: E402

FIG = ROOT / "docs" / "figures"
TAB = ROOT / "docs" / "report" / "tables"
WORK = ROOT / "results" / "work"
BLUE, RED, GREY = "#2463a6", "#c74b28", "#6b6b6b"
plt.rcParams.update({"font.size": 8, "axes.titlesize": 8, "axes.labelsize": 8, "legend.fontsize": 7,
                     "xtick.labelsize": 7, "ytick.labelsize": 7})


def load_rows():
    path = ROOT / "results" / "summary.json"
    if not path.exists():
        sys.exit(f"{path} not found; run scripts/run_experiments.py first")
    return {r["case_id"]: r for r in json.loads(path.read_text(encoding="utf-8"))}


def config_of(row):
    return Config(aw=row["aw"], rom_arch=row["rom_arch"], ftw_car=row["ftw_car"], ftw_msg=row["ftw_msg"],
                  amp_car=row["amp_car"], amp_msg=row["amp_msg"])


def rtl_samples(case_id, latency=3):
    return np.array(read_samples(WORK / case_id / "am_out.txt")[latency:], dtype=float)


def envelope(case_id):
    with open(WORK / case_id / "trace.csv", newline="", encoding="utf-8") as fh:
        return np.array([int(r["env"]) for r in csv.DictReader(fh)], dtype=float)


# --------------------------------------------------------------------------- figures
def box(ax, x, y, w, h, text, fc="#dce6f2"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02", fc=fc, ec=BLUE, lw=1.1))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=7)


def arrow(ax, x1, y1, x2, y2, label=None):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="->", color="#333", lw=1.0))
    if label:
        ax.text((x1 + x2) / 2, y1 + 0.13, label, ha="center", fontsize=6.5, color=GREY)


def block_diagram():
    fig, ax = plt.subplots(figsize=(7.16, 2.5), dpi=300)
    ax.set_xlim(0, 10.6)
    ax.set_ylim(0, 6.2)
    ax.axis("off")
    box(ax, 0.2, 4.2, 2.3, 1.1, "message NCO\nphase_acc + ROM")
    box(ax, 0.2, 0.9, 2.3, 1.1, "carrier NCO\nphase_acc + ROM")
    box(ax, 3.6, 4.2, 2.8, 1.1, "am_envelope\nA_c + (A_m*msg)>>>11")
    box(ax, 3.6, 0.9, 2.8, 1.1, "1-clock delay", fc="#ededed")
    box(ax, 7.3, 2.55, 2.4, 1.1, "am_multiplier\n(env*car)>>>11", fc="#fce4d6")
    ax.text(0.2, 5.75, "ftw_msg", fontsize=7); arrow(ax, 1.3, 5.7, 1.3, 5.32)
    ax.text(0.2, 0.15, "ftw_car", fontsize=7); arrow(ax, 1.3, 0.4, 1.3, 0.88)
    ax.text(3.6, 5.75, "amp_msg, amp_car", fontsize=7); arrow(ax, 5.0, 5.7, 5.0, 5.32)
    arrow(ax, 2.5, 4.75, 3.6, 4.75, "msg")
    arrow(ax, 2.5, 1.45, 3.6, 1.45, "car")
    arrow(ax, 6.4, 4.75, 8.5, 4.75); arrow(ax, 8.5, 4.75, 8.5, 3.67, "env")
    arrow(ax, 6.4, 1.45, 8.5, 1.45); arrow(ax, 8.5, 1.45, 8.5, 2.53)
    arrow(ax, 9.7, 3.1, 10.5, 3.1); ax.text(9.0, 3.85, "am_out", fontsize=7)
    ax.text(5.0, 3.1, "ROM: full 2^AW words\nor quarter 2^(AW-2) words", ha="center", va="center", fontsize=6.5, color=RED)
    fig.savefig(FIG / "block_diagram.png", bbox_inches="tight")
    plt.close(fig)


def time_panel(ax, case_id, rows, title):
    config = config_of(rows[case_id])
    y = rtl_samples(case_id)
    t = np.arange(len(y)) / config.clock_hz * 1e6
    env = envelope(case_id)
    ax.plot(t, y, lw=0.5, color=BLUE)
    ax.plot(t, env, "--", lw=0.9, color=RED)
    ax.plot(t, -env, "--", lw=0.9, color=RED)
    ax.set(xlabel="time (us)", title=title)
    ax.grid(alpha=0.25)


def spectrum_zoom(ax, case_id, rows, title):
    config = config_of(rows[case_id])
    f, a = fft_amplitude(rtl_samples(case_id), config.clock_hz)
    fc = config.ftw_car * config.clock_hz / (1 << config.pw)
    keep = (f > fc - 60e3) & (f < fc + 60e3)
    ref = a[keep].max()
    db = 20 * np.log10(np.maximum(a[keep] / ref, 1e-7))
    ax.vlines(f[keep] / 1e6, -120, db, colors=BLUE, lw=1.0)
    ax.plot(f[keep] / 1e6, db, "o", ms=2.5, color=BLUE)
    ax.set(xlabel="frequency (MHz)", ylim=(-120, 8), title=title)
    ax.grid(alpha=0.25)


def waveforms_and_spectra(rows):
    fig, axes = plt.subplots(2, 3, figsize=(7.16, 4.0), dpi=300)
    time_panel(axes[0, 0], "functional_mu_0.5", rows, r"(a) $\mu=0.5$")
    time_panel(axes[0, 1], "functional_mu_1.5", rows, r"(b) $\mu=1.5$ (overmodulation)")
    time_panel(axes[0, 2], "functional_dsb_sc", rows, r"(c) DSB-SC ($A_c=0$)")
    axes[0, 0].set_ylabel("am_out (LSB)")
    config = config_of(rows["functional_mu_0.5"])
    result = analyze_am(rtl_samples("functional_mu_0.5"), config)
    f, a = fft_amplitude(rtl_samples("functional_mu_0.5"), config.clock_hz)
    db = 20 * np.log10(np.maximum(a / a.max(), 1e-7))
    ax = axes[1, 0]
    ax.plot(f / 1e6, db, lw=0.6, color=BLUE)
    spur = result["largest_spur_hz"] / 1e6
    ax.annotate(f"largest spur\n{spur:g} MHz\n(SFDR {result['sfdr_db']:.1f} dB)", xy=(spur, -result["sfdr_db"]),
                xytext=(spur - 30, -9), va="top", fontsize=6.5, color=RED,
                arrowprops=dict(arrowstyle="->", color=RED))
    ax.set(xlabel="frequency (MHz)", ylabel="dB re largest bin", xlim=(0, 50), ylim=(-120, 5),
           title=r"(d) $\mu=0.5$, full band")
    ax.grid(alpha=0.25)
    spectrum_zoom(axes[1, 1], "functional_mu_0.5", rows, r"(e) $\mu=0.5$, around carrier")
    spectrum_zoom(axes[1, 2], "functional_dsb_sc", rows, "(f) DSB-SC, around 1 MHz")
    fig.tight_layout()
    fig.savefig(FIG / "waveforms_spectra.png")
    plt.close(fig)


def sfdr_and_memory(rows):
    aws = (8, 10, 12)
    full = [rows[f"rom_aw{a}_full"]["sfdr_db"] for a in aws]
    quarter = [rows[f"rom_aw{a}_quarter"]["sfdr_db"] for a in aws]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.16, 2.4), dpi=300)
    a1.plot(aws, [6.02 * a for a in aws], "--", color=GREY, label="6.02 AW")
    a1.plot(aws, full, "o-", color=BLUE, label="full-cycle ROM")
    a1.plot(aws, quarter, "x", color=RED, ms=8, label="quarter-wave ROM")
    a1.set(xticks=aws, xlabel="AW (ROM address bits)", ylabel="SFDR (dB)", title="(a) measured SFDR")
    a1.grid(alpha=0.25)
    a1.legend()
    w = 0.38
    a2.bar([i - w / 2 for i in range(3)], [(1 << a) * 12 for a in aws], w, color=BLUE, label="full-cycle")
    a2.bar([i + w / 2 for i in range(3)], [(1 << (a - 2)) * 12 for a in aws], w, color=RED, label="quarter-wave")
    for i, a in enumerate(aws):
        a2.text(i - w / 2, (1 << a) * 12 * 1.12, f"{(1 << a) * 12:,}", ha="center", fontsize=6.5)
        a2.text(i + w / 2, (1 << (a - 2)) * 12 * 1.12, f"{(1 << (a - 2)) * 12:,}", ha="center", fontsize=6.5)
    a2.set(yscale="log", xticks=range(3), xticklabels=[f"AW={a}" for a in aws], ylabel="table size (bits)",
           ylim=(300, 150000), title="(b) sine table size")
    a2.grid(alpha=0.25, axis="y")
    a2.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(FIG / "sfdr_and_memory.png")
    plt.close(fig)


# --------------------------------------------------------------------------- tables
def fmt(value, digits=2, dash="--"):
    return dash if value is None else f"{value:.{digits}f}"


def cases_table(rows):
    lines = [r"\begin{table*}[t]", r"\caption{Verification results for the 13 configurations (10\,000 samples each; "
             r"SFDR from a Hann-windowed FFT of the RTL output).}", r"\label{tab:cases}", r"\centering", r"\small",
             r"\begin{tabular}{@{}rccrrcccrc@{}}", r"\toprule",
             r"\# & AW & ROM & $A_c$ & $A_m$ & $\mu$ & Envelope range & Output range & Mismatches & SFDR (dB)\\",
             r"\midrule"]
    for n, row in enumerate(rows.values(), 1):
        mu = "--" if row["mu"] is None else f"{row['mu']:g}"
        lines.append(f"{n} & {row['aw']} & {row['rom_arch'].capitalize()} & {row['amp_car']} & {row['amp_msg']} & {mu} & "
                     f"{row['env_min']}\\ldots{row['env_max']} & {row['out_min']}\\ldots{row['out_max']} & "
                     f"{row['mismatch_count']} & {fmt(row['sfdr_db'], 1)}\\\\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table*}"]
    (TAB / "tab_cases.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")


def resources_table(rows):
    lines = [r"\begin{table*}[t]", r"\caption{Post-implementation results, xc7a35tcpg236-1, 100~MHz target "
             r"(out-of-context). $F_{max}=1/(10\,\mathrm{ns}-\mathrm{WNS})$.}", r"\label{tab:res}", r"\centering",
             r"\small", r"\begin{tabular}{@{}clrrrrrrrrr@{}}", r"\toprule",
             r"AW & ROM & Table bits & LUT & FF & LUTRAM & BRAM & DSP & WNS (ns) & $F_{max}$ (MHz) & $P_{dyn}$ (W)\\",
             r"\midrule"]
    for aw in (8, 10, 12):
        for arch in ("full", "quarter"):
            row = rows[f"rom_aw{aw}_{arch}"]
            bits = (1 << aw) * 12 if arch == "full" else (1 << (aw - 2)) * 12
            lines.append(f"{aw} & {arch.capitalize()} & {bits:,} & ".replace(",", r"\,", 1) +
                         " & ".join([str(row[k]) if row[k] is not None else "--" for k in ("lut", "ff", "lutram")] +
                                     [fmt(row["bram"], 1) if row["bram"] is not None else "--",
                                      str(row["dsp"]) if row["dsp"] is not None else "--",
                                      fmt(row["wns"], 3), fmt(row["fmax_mhz"], 1), fmt(row["power_dynamic_w"], 3)]) + r"\\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table*}"]
    (TAB / "tab_resources.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    TAB.mkdir(parents=True, exist_ok=True)
    rows = load_rows()
    block_diagram()
    waveforms_and_spectra(rows)
    sfdr_and_memory(rows)
    cases_table(rows)
    resources_table(rows)
    print("figures:", ", ".join(sorted(p.name for p in FIG.glob("*.png"))))
    print("tables: ", ", ".join(sorted(p.name for p in TAB.glob("*.tex"))))


if __name__ == "__main__":
    main()
