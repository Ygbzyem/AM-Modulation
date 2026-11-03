"""Write results/results.xlsx (Summary, Figures, Spectrum) from the rows built by run_experiments.py."""
from __future__ import annotations

import math
from pathlib import Path

from openpyxl import Workbook
from openpyxl.drawing.image import Image
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

SUMMARY_COLUMNS = [
    ("Case", "case_id"), ("Group", "group"), ("Note", "note"),
    ("AW", "aw"), ("ROM", "rom_arch"),
    ("ftw_car", "ftw_car"), ("ftw_msg", "ftw_msg"), ("amp_car", "amp_car"), ("amp_msg", "amp_msg"),
    ("mu", "mu"), ("Bandwidth (kHz)", "bandwidth_khz"),
    ("env_min", "env_min"), ("env_max", "env_max"), ("out_min", "out_min"), ("out_max", "out_max"),
    ("Result", "result"), ("Mismatches", "mismatch_count"), ("Latency (clk)", "latency"),
    ("SFDR (dB)", "sfdr_db"),
    ("LUT", "lut"), ("FF", "ff"), ("LUTRAM", "lutram"), ("BRAM (tiles)", "bram"), ("DSP", "dsp"),
    ("WNS (ns)", "wns"), ("Fmax (MHz)", "fmax_mhz"), ("Dynamic power (W)", "power_dynamic_w"),
    ("Report folder", "rpt_dir"),
]

SPECTRUM_COLUMNS = [
    ("Case", None), ("Line", "label"), ("Expected (kHz)", "expected_khz"), ("Measured bin (kHz)", "measured_khz"),
    ("Frequency error (Hz)", "freq_error_hz"), ("Peak amplitude (LSB)", "peak_amplitude"),
    ("Ratio to carrier", "ratio_to_carrier"), ("Ideal ratio", "ideal_ratio_to_carrier"),
    ("Ratio error", "ratio_error"),
]

HEADER_FILL = PatternFill("solid", fgColor="305496")


def _clean(value):
    """NaN and None become empty cells."""
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _header(sheet, titles):
    sheet.append(titles)
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _fit(sheet, minimum=8, maximum=34):
    for column in sheet.columns:
        letter = get_column_letter(column[0].column)
        width = max(len(str(c.value)) if c.value is not None else 0 for c in column)
        sheet.column_dimensions[letter].width = max(minimum, min(maximum, width + 2))


def build(rows, out_path, root) -> Path:
    out_path, root = Path(out_path), Path(root)
    workbook = Workbook()

    summary = workbook.active
    summary.title = "Summary"
    _header(summary, [title for title, _ in SUMMARY_COLUMNS])
    for row in rows:
        values = dict(row)
        values["bandwidth_khz"] = None if row.get("bandwidth_hz") is None else row["bandwidth_hz"] / 1e3
        summary.append([_clean(values.get(key)) for _, key in SUMMARY_COLUMNS])
    summary.freeze_panes = "B2"
    _fit(summary)

    figures = workbook.create_sheet("Figures")
    _header(figures, ["Case", "Waveform", "Spectrum"])
    figures.column_dimensions["A"].width = 26
    figures.column_dimensions["B"].width = 80
    figures.column_dimensions["C"].width = 80
    line = 2
    for row in rows:
        figures.cell(row=line, column=1, value=row["case_id"])
        placed = False
        for column, key in ((2, "waveform"), (3, "spectrum")):
            path = (row.get("figures") or {}).get(key)
            if path and (root / path).exists():
                image = Image(str(root / path))
                scale = 560 / image.width
                image.width, image.height = 560, int(image.height * scale)
                figures.add_image(image, f"{get_column_letter(column)}{line}")
                placed = True
                height = image.height
        figures.row_dimensions[line].height = (height * 0.75 + 6) if placed else 15
        line += 1

    spectrum = workbook.create_sheet("Spectrum")
    _header(spectrum, [title for title, _ in SPECTRUM_COLUMNS])
    for row in rows:
        for entry in row.get("spectrum") or []:
            values = dict(entry)
            values["expected_khz"] = entry["expected_hz"] / 1e3
            values["measured_khz"] = entry["measured_bin_hz"] / 1e3
            spectrum.append([row["case_id"] if key is None else _clean(values.get(key)) for _, key in SPECTRUM_COLUMNS])
    spectrum.freeze_panes = "C2"
    _fit(spectrum)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(out_path)
    return out_path
