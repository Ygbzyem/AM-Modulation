"""Waveform, envelope, RTL comparison, and spectrum figures."""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

try:
    from .am_golden import Config, generate
    from .compare import compare, read_samples
    from .spectrum import fft_amplitude
except ImportError:
    from am_golden import Config, generate
    from compare import compare, read_samples
    from spectrum import fft_amplitude


def plot_waveform(samples, config, path, rows=None, rtl=None, title="AM reference model"):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    time_us = (np.arange(len(samples)) + config.start_sample) / config.clock_hz * 1e6
    fig, axes = plt.subplots(2 if rtl is not None else 1, 1, figsize=(12, 4.8 if rtl is None else 7), squeeze=False)
    axis = axes[0, 0]
    axis.plot(time_us, samples, color="#2463a6", linewidth=0.65, label="Golden output" if rtl is not None else "Output")
    if rows is not None:
        envelope = np.array([row["env"] for row in rows])
        axis.plot(time_us, envelope, "--", color="#c74b28", linewidth=1.3, label="Signed env and -env")
        axis.plot(time_us, -envelope, "--", color="#c74b28", linewidth=1.3)
    if rtl is not None:
        if len(rtl) != len(samples):
            raise ValueError("Cannot overlay streams of different lengths")
        axis.plot(time_us, rtl, color="#2a9259", linewidth=0.6, alpha=0.65, label="RTL output")
        axes[1, 0].plot(time_us, np.asarray(rtl) - np.asarray(samples), color="#c74b28", linewidth=0.7)
        axes[1, 0].set(xlabel="Time (us)", ylabel="RTL - golden (LSB)")
        axes[1, 0].grid(alpha=0.2)
    axis.set(xlabel="Time (us)", ylabel="Signed integer amplitude", title=title)
    axis.grid(alpha=0.2)
    axis.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def plot_spectrum(samples, config, path, title="Golden model spectrum"):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frequencies, amplitudes = fft_amplitude(samples, config.clock_hz)
    reference = max(float(np.max(amplitudes)), 1e-30)
    decibels = 20 * np.log10(np.maximum(amplitudes / reference, 1e-7))
    fc = config.ftw_car * config.clock_hz / (1 << config.pw)
    fm = config.ftw_msg * config.clock_hz / (1 << config.pw)
    fig, axes = plt.subplots(2, 1, figsize=(10, 7))
    for axis in axes:
        axis.plot(frequencies / 1e6, decibels, linewidth=0.8, color="#2463a6")
        axis.set(xlabel="Frequency (MHz)", ylabel="dB relative to largest FFT bin", ylim=(-120, 5))
        axis.grid(alpha=0.2)
    axes[0].set(title=title, xlim=(0, config.clock_hz / 2e6))
    axes[1].set(xlim=(max(0, (fc - max(4 * fm, 100_000)) / 1e6),
                       min(config.clock_hz / 2e6, (fc + max(4 * fm, 100_000)) / 1e6)),
                ylim=(-120, 18), title="Carrier and sidebands (periodic Hann window)")
    # Show discrete bins in the zoom so separate sidebands stay visible.
    axes[1].lines[0].remove()
    limits = axes[1].get_xlim()
    visible = (frequencies / 1e6 >= limits[0]) & (frequencies / 1e6 <= limits[1])
    marker, stems, baseline = axes[1].stem(frequencies[visible] / 1e6, decibels[visible], bottom=-120)
    plt.setp(marker, markersize=3, color="#2463a6")
    plt.setp(stems, linewidth=1, color="#2463a6")
    baseline.set_visible(False)
    for frequency, label, active in ((fc - fm, "fc-fm", config.amp_msg),
                                     (fc, "fc", config.amp_car), (fc + fm, "fc+fm", config.amp_msg)):
        if not active:
            continue
        index = int(round(frequency / (config.clock_hz / len(samples))))
        axes[1].plot(frequencies[index] / 1e6, decibels[index], "o", color="#c74b28", markersize=5)
        axes[1].annotate(f"{label}\n{decibels[index]:.2f} dB", (frequencies[index] / 1e6, decibels[index]),
                         xytext=(0, 7), textcoords="offset points", ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("golden", type=Path)
    parser.add_argument("--rtl", type=Path)
    parser.add_argument("--skip-rtl", type=int, default=0)
    parser.add_argument("--output-dir", type=Path, default=Path("results/plots"))
    parser.add_argument("--metadata", type=Path, help="metadata JSON emitted by am_golden.py")
    args = parser.parse_args()
    golden = read_samples(args.golden)
    rows = None
    if args.metadata:
        import json
        config = Config(**json.loads(args.metadata.read_text(encoding="utf-8"))["config"])
        rows = generate(config)
        if golden != [row["out"] for row in rows]:
            raise ValueError("Golden file does not match supplied metadata")
    else:
        config = Config(samples=len(golden))
    rtl = None
    result = None
    if args.rtl:
        result = compare(args.golden, args.rtl, skip_rtl=args.skip_rtl, expected_samples=len(golden))
        print(result)
        rtl = read_samples(args.rtl)[args.skip_rtl:]
    plot_waveform(golden, config, args.output_dir / "waveform.png", rows, rtl)
    plot_spectrum(golden, config, args.output_dir / "spectrum.png")
    return 1 if result and not result["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
