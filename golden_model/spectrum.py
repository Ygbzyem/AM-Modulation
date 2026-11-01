"""Hann-window FFT measurements with explicit wanted-tone exclusion."""
import argparse
import csv
import json
from pathlib import Path

import numpy as np

try:
    from .compare import read_samples
except ImportError:
    from compare import read_samples


def fft_amplitude(samples, sample_rate):
    values = np.asarray(samples, dtype=float)
    if len(values) < 16 or sample_rate <= 0 or not np.all(np.isfinite(values)):
        raise ValueError("Need at least 16 finite samples and a positive sample rate")
    # Periodic Hann; normalize for peak amplitude of a coherent sinusoid.
    window = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(len(values)) / len(values))
    amplitude = 2 * np.abs(np.fft.rfft(values * window)) / window.sum()
    amplitude[0] /= 2
    if len(values) % 2 == 0:
        amplitude[-1] /= 2
    frequencies = np.fft.rfftfreq(len(values), 1 / sample_rate)
    return frequencies, amplitude


def measure(samples, sample_rate, wanted_hz, guard_bins=3):
    """SFDR relative to strongest desired FFT peak, excluding ±guard bins.

    This is a finite-record, windowed FFT estimate, including DC as a spur.
    Guard bands can overlap; their union is excluded. Wanted centers must
    remain at least two FFT bins apart to separate Hann-window peaks.
    """
    if guard_bins < 1 or not wanted_hz:
        raise ValueError("Require guard_bins >= 1 and at least one wanted tone")
    frequencies, amplitudes = fft_amplitude(samples, sample_rate)
    bin_hz = sample_rate / len(samples)
    if any(not 0 < tone < sample_rate / 2 for tone in wanted_hz):
        raise ValueError("Wanted tones must lie strictly between DC and Nyquist")
    centers = sorted(int(round(tone / bin_hz)) for tone in wanted_hz)
    if len(centers) > 1 and min(np.diff(centers)) < 2:
        raise ValueError("Record too short to separate wanted-tone centers; increase samples")
    eligible = np.ones(len(amplitudes), dtype=bool)
    tones = []
    for tone in wanted_hz:
        center = int(round(tone / bin_hz))
        low, high = max(0, center - guard_bins), min(len(amplitudes), center + guard_bins + 1)
        eligible[low:high] = False
        # Nearest expected bin avoids assigning a nearby tone's peak.
        tones.append({"expected_hz": float(tone), "bin_hz": float(frequencies[center]),
                      "peak_amplitude": float(amplitudes[center]), "bin": center})
    reference = max(tone["peak_amplitude"] for tone in tones)
    indices = np.flatnonzero(eligible)
    spur_index = int(indices[np.argmax(amplitudes[indices])]) if len(indices) else None
    spur = float(amplitudes[spur_index]) if spur_index is not None else 0.0
    sfdr = float(20 * np.log10(reference / spur)) if reference > 0 and spur > 0 else None
    return {"samples": len(samples), "sample_rate_hz": sample_rate, "bin_width_hz": bin_hz,
            "window": "periodic Hann; coherent-gain corrected; single-sided peak amplitude",
            "guard_bins": guard_bins, "dc_treated_as_spur": True,
            "reference_peak_amplitude": reference, "wanted_tones": tones,
            "sfdr_db": sfdr, "largest_spur_hz": float(frequencies[spur_index]) if spur_index is not None else None,
            "largest_spur_amplitude": spur,
            "limitation": "Windowed finite-record estimate; wanted bands excluded, including their in-band distortion. Noncoherent leakage may limit SFDR."}


def analyze_am(samples, config):
    fc = config.ftw_car * config.clock_hz / (1 << config.pw)
    fm = config.ftw_msg * config.clock_hz / (1 << config.pw)
    if not 0 < fm < fc or fc + fm >= config.clock_hz / 2:
        raise ValueError("AM spectrum helper requires 0 < fm < fc and fc+fm < Nyquist")
    if config.amp_car == config.amp_msg == 0:
        raise ValueError("Zero signal has no SFDR reference")
    wanted = ([fc] if config.amp_car else []) + ([fc - fm, fc + fm] if config.amp_msg else [])
    result = measure(samples, config.clock_hz, sorted(wanted))
    result["definition"] = "AM SFDR: strongest intended line / largest FFT bin outside intended-line guard bands"
    frequencies, amplitudes = fft_amplitude(samples, config.clock_hz)
    carrier = float(amplitudes[int(round(fc / result["bin_width_hz"]))])
    theoretical_ratio = config.amp_msg / (2 * config.amp_car) if config.amp_car else None
    result["mu"] = config.amp_msg / config.amp_car if config.amp_car else None
    result["ideal_bandwidth_hz"] = 2 * fm if config.amp_msg else 0.0
    result["lines"] = []
    for label, frequency in (("lower_sideband", fc - fm), ("carrier", fc), ("upper_sideband", fc + fm)):
        index = int(round(frequency / result["bin_width_hz"]))
        measured = float(amplitudes[index])
        ratio = measured / carrier if config.amp_car and carrier else None
        ideal = 1.0 if label == "carrier" and config.amp_car else (theoretical_ratio if label != "carrier" else None)
        result["lines"].append({"label": label, "expected_hz": frequency,
                                "measured_bin_hz": float(frequencies[index]), "peak_amplitude": measured,
                                "ratio_to_carrier": ratio, "ideal_ratio_to_carrier": ideal,
                                "ratio_error": ratio - ideal if ratio is not None and ideal is not None else None})
    result["ratio_note"] = "Ratios are textbook mu/2 estimates; finite DW, shift-by-11 quantization and window detuning cause differences. DSB-SC ratios are undefined."
    return result


def save_fft_csv(samples, sample_rate, path):
    frequencies, amplitudes = fft_amplitude(samples, sample_rate)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["frequency_hz", "peak_amplitude"])
        writer.writerows(zip(frequencies, amplitudes))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--sample-rate", type=float, default=100_000_000)
    parser.add_argument("--wanted-hz", type=float, nargs="+", required=True)
    parser.add_argument("--guard-bins", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("spectrum.json"))
    parser.add_argument("--csv", type=Path)
    args = parser.parse_args()
    samples = read_samples(args.input)
    result = measure(samples, args.sample_rate, args.wanted_hz, args.guard_bins)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if args.csv:
        save_fft_csv(samples, args.sample_rate, args.csv)
    value = result["sfdr_db"]
    print(f"FFT estimate SFDR: {value:.2f} dB" if value is not None else "SFDR undefined (no nonzero reference or spur)")


if __name__ == "__main__":
    main()
