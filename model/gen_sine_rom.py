"""Generate midpoint sine tables and verify all quarter-wave addresses."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def sine_tables(aw=8, dw=12):
    if not 3 <= aw <= 16 or not 2 <= dw <= 24:
        raise ValueError("Require 3 <= AW <= 16 and 2 <= DW <= 24")
    size = 1 << aw
    peak = (1 << (dw - 1)) - 1
    full = [round(peak * math.sin(2 * math.pi * (n + 0.5) / size))
            for n in range(size)]
    quarter = full[:size // 4]
    reconstructed = [quarter_lookup(quarter, p, aw) for p in range(size)]
    if reconstructed != full:
        raise AssertionError("Quarter reconstruction differs from direct full sine table")
    return full, quarter


def quarter_lookup(quarter, address, aw):
    mask = (1 << (aw - 2)) - 1
    index = address & mask
    if address & (1 << (aw - 2)):
        index ^= mask
    value = quarter[index]
    return -value if address & (1 << (aw - 1)) else value


def generate_all(output_dir, widths=(8, 10, 12), dw=12):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for aw in widths:
        full, quarter = sine_tables(aw, dw)
        for architecture, table in (("full", full), ("quarter", quarter)):
            path = output_dir / f"sine_{architecture}_AW{aw}.mem"
            digits = (dw + 3) // 4
            content = "".join(f"{value & ((1 << dw) - 1):0{digits}X}\n" for value in table)
            path.write_text(content, encoding="ascii", newline="")
            records.append({"file": path.name, "aw": aw, "dw": dw,
                            "architecture": architecture.upper(), "entries": len(table),
                            "logical_bits": len(table) * dw,
                            "sha256": hashlib.sha256(content.encode("ascii")).hexdigest()})
    manifest = {"formula": "round((2**(DW-1)-1)*sin(2*pi*(n+0.5)/2**AW))",
                "encoding": "one two's-complement hexadecimal word per line; no header",
                "quarter_reconstruction": "PASS at every address for every AW",
                "tables": records}
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("mem"))
    parser.add_argument("--aw", nargs="+", type=int, default=[8, 10, 12])
    parser.add_argument("--dw", type=int, default=12)
    args = parser.parse_args()
    result = generate_all(args.output_dir, args.aw, args.dw)
    print(f"PASS: {len(result['tables'])} ROM files; full/quarter equal at every address")


if __name__ == "__main__":
    main()
