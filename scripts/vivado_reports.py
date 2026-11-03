"""Parse Vivado utilization, timing and power reports."""
from __future__ import annotations

import math
import re
from pathlib import Path

CLOCK_PERIOD_NS = 10.0


def _table_rows(text: str):

    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2:
            yield cells[0].rstrip("*").strip(), cells[1:]


def _first_number(rows, name: str):

    for label, cells in rows:
        if label == name:
            try:
                value = float(cells[0])
            except ValueError:
                return None
            return int(value) if value.is_integer() else value
    return None


def parse_utilization(path) -> dict:
    path = Path(path)
    rows = list(_table_rows(path.read_text(encoding="utf-8", errors="ignore")))
    wanted = {
        "lut": "Slice LUTs",
        "lut_logic": "LUT as Logic",
        "lutram": "LUT as Memory",
        "ff": "Slice Registers",
        "bram": "Block RAM Tile",
        "dsp": "DSPs",
    }
    out = {}
    for key, label in wanted.items():
        value = _first_number(rows, label)
        if value is None:
            raise ValueError(f"{path}: row not found: '{label}' ({key})")
        out[key] = value
    return out


def parse_timing(path) -> dict:

    path = Path(path)
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    for i, line in enumerate(lines):
        if "WNS(ns)" not in line:
            continue
        header = [h for h in re.split(r"\s{2,}", line.strip()) if h]
        for value_line in lines[i + 1 : i + 6]:
            tokens = value_line.split()
            if len(tokens) == len(header) and re.fullmatch(r"-?[\d.]+|inf|-inf|NA", tokens[0]):
                row = dict(zip(header, tokens))

                def num(key):
                    raw = row[key]
                    return float(raw) if raw not in ("NA",) else math.nan

                return {
                    "wns": num("WNS(ns)"),
                    "tns": num("TNS(ns)"),
                    "whs": num("WHS(ns)"),
                    "failing_endpoints": int(row["TNS Failing Endpoints"]),
                }
        break
    raise ValueError(f"{path}: Design Timing Summary not found")


def fmax_mhz(wns_ns: float, period_ns: float = CLOCK_PERIOD_NS) -> float:

    if math.isnan(wns_ns) or math.isinf(wns_ns):
        return math.nan
    return 1000.0 / (period_ns - wns_ns)


def parse_power(path) -> dict:
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="ignore")
    out = {}
    for key, label in (("power_total_w", "Total On-Chip Power (W)"),
                       ("power_dynamic_w", "Dynamic (W)"),
                       ("power_static_w", "Device Static (W)")):
        m = re.search(r"\|\s*" + re.escape(label) + r"\s*\|\s*([\d.]+)", text)
        if not m:
            raise ValueError(f"{path}: not found: '{label}'")
        out[key] = float(m.group(1))
    return out


def parse_impl_dir(directory) -> dict:

    directory = Path(directory)
    result = {}
    result.update(parse_utilization(directory / "utilization.rpt"))
    timing = parse_timing(directory / "timing.rpt")
    result.update(timing)
    result["fmax_mhz"] = fmax_mhz(timing["wns"])
    result.update(parse_power(directory / "power.rpt"))
    return result
