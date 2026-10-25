"""Strict decimal sample-file comparison. Never searches for a passing offset."""
import argparse
import json
import re
from pathlib import Path


def read_samples(path):
    values = []
    for line_number, raw in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), 1):
        text = raw.strip()
        if not text:
            continue
        if not re.fullmatch(r"[+-]?[0-9]+", text):
            raise ValueError(f"{path}:{line_number}: expected one decimal integer, got {text!r}")
        value = int(text)
        if not -32768 <= value <= 32767:
            raise ValueError(f"{path}:{line_number}: sample outside signed 16-bit range")
        values.append(value)
    if not values:
        raise ValueError(f"{path}: no samples")
    return values


def compare(golden_path, rtl_path, *, skip_rtl=0, expected_samples=10_000):
    """Return JSON-serializable result; raise on bad options. Errors in files => FAIL.

    n_compared is overlap; mismatches counts differing values in that overlap.
    Length differences fail independently. first_mismatch is zero-based in the
    retained stream; original_rtl_index includes explicitly skipped samples.
    """
    if skip_rtl < 0 or expected_samples <= 0:
        raise ValueError("skip_rtl must be nonnegative and expected_samples positive")
    result = {"passed": False, "status": "FAIL", "expected_samples": expected_samples,
              "skip_rtl": skip_rtl, "n_golden": None, "n_rtl_raw": None, "n_rtl": None,
              "n_compared": 0, "mismatches": 0, "missing_samples": 0, "extra_samples": 0,
              "max_abs_error": None, "first_mismatch": None, "error": None}
    try:
        golden = read_samples(golden_path)
        rtl_raw = read_samples(rtl_path)
    except (OSError, ValueError) as exc:
        result["error"] = str(exc)
        return result
    rtl = rtl_raw[skip_rtl:]
    result.update(n_golden=len(golden), n_rtl_raw=len(rtl_raw), n_rtl=len(rtl))
    result["missing_samples"] = max(0, len(golden) - len(rtl))
    result["extra_samples"] = max(0, len(rtl) - len(golden))
    maximum = 0
    for index, (reference, actual) in enumerate(zip(golden, rtl)):
        result["n_compared"] += 1
        maximum = max(maximum, abs(reference - actual))
        if reference != actual:
            result["mismatches"] += 1
            if result["first_mismatch"] is None:
                result["first_mismatch"] = {"index": index, "original_rtl_index": index + skip_rtl,
                                             "golden": reference, "rtl": actual}
    result["max_abs_error"] = maximum if result["n_compared"] else None
    if len(golden) != expected_samples or len(rtl) != expected_samples:
        result["error"] = f"Expected exactly {expected_samples} samples in each retained stream"
    result["passed"] = (result["error"] is None and result["mismatches"] == 0)
    result["status"] = "PASS" if result["passed"] else "FAIL"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("golden", type=Path)
    parser.add_argument("rtl", type=Path)
    parser.add_argument("--skip-rtl", type=int, default=0)
    parser.add_argument("--expected-samples", type=int, default=10_000)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    result = compare(args.golden, args.rtl, skip_rtl=args.skip_rtl, expected_samples=args.expected_samples)
    text = json.dumps(result, indent=2)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
