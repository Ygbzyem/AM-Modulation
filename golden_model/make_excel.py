"""Collect every verification and synthesis result into results/results.xlsx.

    python golden_model/make_excel.py

Reads whatever exists, so it can be run at any stage:
    results/rtl/<case>/record.json      from verify_rtl.py     (tb_am_regression, 18 cases)
    results/custom/<case>/record.json   from check_result.py   (tb_am_top_filebased runs)
    results/synth/aw<N>_<rom>/          utilization.rpt, timing.rpt, optional power.rpt

Sheets:
    Summary    one row per case: inputs, RTL-vs-golden result, measurements, resources
    Figures    golden-vs-RTL waveform and spectrum images for every case
    Spectrum   carrier and sideband lines measured on the RTL output
    Resources  the six synthesis configurations and the Full-vs-Quarter comparison
    Settings   constants the formulas use, and where every number comes from
"""
import argparse
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for entry in (str(HERE), str(ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from openpyxl import Workbook
from openpyxl.drawing.image import Image
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

try:
    from am_golden import Config
    from compare import read_samples
    from spectrum import analyze_am
    from vivado_reports import parse_impl_dir
except ImportError:
    from golden_model.am_golden import Config
    from golden_model.compare import read_samples
    from golden_model.spectrum import analyze_am
    from golden_model.vivado_reports import parse_impl_dir

FONT = "Arial"
HEADER_FILL = PatternFill("solid", fgColor="305496")
PASS_FILL = PatternFill("solid", fgColor="C6EFCE")
FAIL_FILL = PatternFill("solid", fgColor="FFC7CE")
SECTION_FILL = PatternFill("solid", fgColor="D9E1F2")
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
TOP = "am_modulator_top"
CONFIGS = [(aw, rom) for aw in (8, 10, 12) for rom in ("FULL", "QUARTER")]
IMAGE_WIDTH = 620


def tag(aw, rom):
    return f"aw{aw}_{rom.lower()}"


def clean(value):
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def style_header(sheet, row=1):
    for cell in sheet[row]:
        if cell.value is None:
            continue
        cell.font = Font(name=FONT, bold=True, color="FFFFFF")
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BOX
    sheet.row_dimensions[row].height = 32


def style_body(sheet, first_row, last_row, last_col):
    for row in sheet.iter_rows(min_row=first_row, max_row=last_row, max_col=last_col):
        for cell in row:
            cell.font = Font(name=FONT, size=10, bold=cell.font.bold if cell.font else False,
                             color=cell.font.color if cell.font and cell.font.color else None)
            cell.border = BOX
            cell.alignment = Alignment(vertical="center")


def note(sheet, row, text, col=1):
    cell = sheet.cell(row=row, column=col, value=text)
    cell.font = Font(name=FONT, size=9, italic=True, color="595959")
    return cell


# ------------------------------------------------------------------ inputs
def load_records():
    records = []
    for source, folder in (("regression", ROOT / "results" / "rtl"), ("custom", ROOT / "results" / "custom")):
        for path in sorted(folder.glob("*/record.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            record["source"] = source
            record["dir"] = path.parent
            records.append(record)
    records.sort(key=lambda r: (r["source"] != "regression", r.get("index") or 0, r["case"]))
    return records


def load_synth():
    found = {}
    for aw, rom in CONFIGS:
        for directory in (ROOT / "results" / "synth" / tag(aw, rom),
                          ROOT / "results" / "rpt" / f"AW{aw}_{rom}"):
            if (directory / "utilization.rpt").exists() and (directory / "timing.rpt").exists():
                try:
                    data = parse_impl_dir(directory)
                except ValueError as error:
                    print(f"WARNING: {error}")
                    break
                if data.get("design") != TOP:
                    print(f"WARNING: {directory.relative_to(ROOT)} reports design '{data.get('design')}', "
                          f"not '{TOP}'. Set {TOP} as the synthesis top and rerun; skipped.")
                    break
                found[(aw, rom)] = {**data, "dir": directory}
                break
    return found


def config_of(record):
    return Config(clock_hz=record.get("clock_hz", 100_000_000), aw=record["aw"], rom_arch=record["rom"],
                  ftw_car=record["ftw_car"], ftw_msg=record["ftw_msg"],
                  amp_car=record["amp_car"], amp_msg=record["amp_msg"], samples=record["samples"])


# ------------------------------------------------------------------ sheets
def sheet_settings(book):
    sheet = book.create_sheet("Settings")
    sheet.append(["Name", "Value", "Unit", "Source"])
    sheet.append(["Clock frequency", 100_000_000, "Hz", "constraint/constraints.xdc, create_clock -period 10.000"])
    sheet.append(["Clock period", "=1E9/B2", "ns", "derived from B2"])
    sheet.append(["Phase accumulator width", 32, "bit", "src/am_modulator_top.v, PW"])
    sheet.append(["FTW per Hz", "=2^B4/B2", "1/Hz", "derived: FTW = f x 2^PW / f_clk"])
    style_header(sheet)
    style_body(sheet, 2, 5, 4)
    sheet["B2"].number_format = "#,##0"
    sheet["B3"].number_format = "0.000"
    sheet["B5"].number_format = "0.00000000"
    for col, width in zip("ABCD", (26, 16, 8, 62)):
        sheet.column_dimensions[col].width = width
    note(sheet, 7, "Inputs come from the testbench header of every RTL output file; measurements come from "
                   "golden_model/verify_rtl.py and check_result.py; resources from the Vivado reports.")
    note(sheet, 8, "Regenerate this workbook with: python golden_model/make_excel.py")
    return sheet


def sheet_resources(book, synth):
    sheet = book.create_sheet("Resources")
    titles = ["Config", "AW", "ROM", "LUT", "LUT as logic", "LUTRAM", "FF", "BRAM (tiles)", "DSP",
              "WNS (ns)", "Fmax (MHz)", "Dynamic power (W)", "Report folder"]
    sheet.append(titles)
    for row, (aw, rom) in enumerate(CONFIGS, start=2):
        data = synth.get((aw, rom), {})
        sheet.append([tag(aw, rom), aw, rom,
                      data.get("lut"), data.get("lut_logic"), data.get("lutram"), data.get("ff"),
                      data.get("bram"), data.get("dsp"), clean(data.get("wns")),
                      f'=IF(ISNUMBER(J{row}),1000/(Settings!$B$3-J{row}),"")',
                      clean(data.get("power_dynamic_w")),
                      str(data["dir"].relative_to(ROOT)).replace("\\", "/") if data else "not run yet"])
    last = 1 + len(CONFIGS)
    style_header(sheet)
    style_body(sheet, 2, last, len(titles))
    for row in range(2, last + 1):
        sheet[f"J{row}"].number_format = "0.000"
        sheet[f"K{row}"].number_format = "0.0"
        sheet[f"L{row}"].number_format = "0.000"

    # Full vs Quarter comparison, all formulas
    start = last + 3
    sheet.cell(row=start - 1, column=1, value="Quarter-wave ROM compared with full-wave ROM").font = \
        Font(name=FONT, bold=True)
    head = ["AW", "Metric", "Full", "Quarter", "Quarter - Full", "Change"]
    for col, text in enumerate(head, start=1):
        sheet.cell(row=start, column=col, value=text)
    style_header(sheet, start)
    metrics = (("LUT", "D"), ("LUTRAM", "F"), ("FF", "G"), ("BRAM (tiles)", "H"), ("DSP", "I"), ("Fmax (MHz)", "K"))
    row = start + 1
    for index, aw in enumerate((8, 10, 12)):
        full_row, quarter_row = 2 + 2 * index, 3 + 2 * index
        for metric, col in metrics:
            sheet.cell(row=row, column=1, value=aw)
            sheet.cell(row=row, column=2, value=metric)
            sheet.cell(row=row, column=3, value=f"={col}{full_row}")
            sheet.cell(row=row, column=4, value=f"={col}{quarter_row}")
            sheet.cell(row=row, column=5, value=f'=IF(AND(ISNUMBER(C{row}),ISNUMBER(D{row})),D{row}-C{row},"")')
            sheet.cell(row=row, column=6,
                       value=f'=IF(AND(ISNUMBER(C{row}),ISNUMBER(D{row}),C{row}<>0),(D{row}-C{row})/C{row},"")')
            sheet.cell(row=row, column=6).number_format = "0.0%"
            for c in (3, 4, 5):
                sheet.cell(row=row, column=c).number_format = "0.0" if metric == "Fmax (MHz)" else "General"
            row += 1
    style_body(sheet, start + 1, row - 1, len(head))
    note(sheet, row + 1, "Fmax = 1000 / (clock period - WNS). Change = (Quarter - Full) / Full; "
                         "negative means the quarter-wave ROM uses less.")
    if not synth:
        note(sheet, row + 2, "No synthesis reports found in results/synth/aw<N>_<rom>/ yet.")
    for col, width in zip("ABCDEFGHIJKLM", (14, 14, 10, 9, 11, 9, 9, 11, 8, 10, 11, 14, 26)):
        sheet.column_dimensions[col].width = width
    sheet.freeze_panes = "B2"
    return sheet


def sheet_summary(book, records):
    sheet = book.active
    sheet.title = "Summary"
    titles = ["Case", "Source", "AW", "ROM", "ftw_car", "ftw_msg", "f_car (kHz)", "f_msg (kHz)",
              "amp_car", "amp_msg", "mu", "Samples", "Mismatches", "Max |error|", "Result",
              "env_min", "env_max", "RTL out_min", "RTL out_max", "SFDR (dB)",
              "LUT", "FF", "BRAM (tiles)", "DSP", "Fmax (MHz)", "Config", "Figures"]
    sheet.append(titles)
    col = {title: get_column_letter(i) for i, title in enumerate(titles, start=1)}
    for row, record in enumerate(records, start=2):
        figure = record["dir"] / "rtl_vs_golden.png"
        values = [record["case"], record["source"], record["aw"], record["rom"],
                  record["ftw_car"], record["ftw_msg"],
                  f"=E{row}/Settings!$B$5/1000", f"=F{row}/Settings!$B$5/1000",
                  record["amp_car"], record["amp_msg"],
                  f'=IF(I{row}=0,"DSB-SC",J{row}/I{row})',
                  record["n_compared"], record["mismatches"], record["max_abs_error"], record["status"],
                  record["env_min"], record["env_max"], record["rtl_out_min"], record["rtl_out_max"],
                  clean(record.get("sfdr_db"))]
        cfg = col["Config"]
        for name, res_col in (("LUT", "D"), ("FF", "G"), ("BRAM (tiles)", "H"), ("DSP", "I"), ("Fmax (MHz)", "K")):
            lookup = f"INDEX(Resources!${res_col}$2:${res_col}$7,MATCH({cfg}{row},Resources!$A$2:$A$7,0))"
            values.append(f'=IFERROR(IF({lookup}="","",{lookup}),"")')
        values.append(tag(record["aw"], record["rom"]))
        values.append("open" if figure.exists() else "")
        sheet.append(values)
        if figure.exists():
            link = sheet.cell(row=row, column=len(titles))
            link.hyperlink = str(figure.relative_to(ROOT / "results")).replace("\\", "/")
            link.font = Font(name=FONT, color="0563C1", underline="single")
        result = sheet[f"{col['Result']}{row}"]
        result.fill = PASS_FILL if record["status"] == "PASS" else FAIL_FILL
        result.font = Font(name=FONT, bold=True)

    last = 1 + len(records)
    style_header(sheet)
    style_body(sheet, 2, last, len(titles))
    for row in range(2, last + 1):
        sheet[f"{col['Result']}{row}"].font = Font(name=FONT, size=10, bold=True)
        sheet[f"{col['Figures']}{row}"].font = Font(name=FONT, size=10, color="0563C1", underline="single")
        for name, fmt in (("f_car (kHz)", "#,##0.000"), ("f_msg (kHz)", "#,##0.000"), ("mu", "0.00"),
                          ("SFDR (dB)", "0.00"), ("Fmax (MHz)", "0.0"), ("ftw_car", "#,##0"), ("ftw_msg", "#,##0")):
            sheet[f"{col[name]}{row}"].number_format = fmt

    passed = sum(r["status"] == "PASS" for r in records)
    note(sheet, last + 2, f"{passed} / {len(records)} cases bit-exact against the Python golden model.")
    note(sheet, last + 3, "f = FTW / (FTW per Hz); mu = amp_msg / amp_car. Resource columns look up the "
                          "matching configuration on the Resources sheet (empty until synthesis has been run).")
    note(sheet, last + 4, "env and RTL out ranges are measured over the simulated record; SFDR is measured on "
                          "the RTL output (periodic Hann window), empty where it is not defined.")
    widths = {"Case": 22, "Source": 11, "ROM": 9, "ftw_car": 12, "ftw_msg": 11, "Result": 8,
              "Config": 12, "Figures": 8}
    for title, letter in col.items():
        sheet.column_dimensions[letter].width = widths.get(title, 10)
    sheet.freeze_panes = "B2"
    sheet.auto_filter.ref = f"A1:{get_column_letter(len(titles))}{last}"
    return sheet


def sheet_figures(book, records):
    sheet = book.create_sheet("Figures")
    sheet.append(["Case", "Result", "Waveform: golden | RTL | error", "Spectrum: golden | RTL"])
    style_header(sheet)
    sheet.column_dimensions["A"].width = 22
    sheet.column_dimensions["B"].width = 9
    sheet.column_dimensions["C"].width = IMAGE_WIDTH / 7
    sheet.column_dimensions["D"].width = IMAGE_WIDTH / 7
    for row, record in enumerate(records, start=2):
        sheet.cell(row=row, column=1, value=record["case"]).font = Font(name=FONT, bold=True)
        result = sheet.cell(row=row, column=2, value=record["status"])
        result.fill = PASS_FILL if record["status"] == "PASS" else FAIL_FILL
        result.font = Font(name=FONT, bold=True)
        for cell in (sheet.cell(row=row, column=1), result):
            cell.alignment = Alignment(vertical="top")
        height = 15
        for column, key in ((3, "waveform"), (4, "spectrum")):
            name = (record.get("figures") or {}).get(key)
            path = record["dir"] / name if name else None
            if path and path.exists():
                image = Image(str(path))
                scale = IMAGE_WIDTH / image.width
                image.width, image.height = IMAGE_WIDTH, int(image.height * scale)
                sheet.add_image(image, f"{get_column_letter(column)}{row}")
                height = max(height, image.height * 0.75 + 6)
        sheet.row_dimensions[row].height = height
    sheet.freeze_panes = "C2"
    return sheet


def sheet_spectrum(book, records):
    sheet = book.create_sheet("Spectrum")
    titles = ["Case", "Line", "Expected (kHz)", "Measured bin (kHz)", "Peak amplitude (LSB)",
              "Ratio to carrier", "Ideal ratio", "Ratio error"]
    sheet.append(titles)
    row = 2
    for record in records:
        rtl_path = record["dir"] / "rtl.txt"
        if not rtl_path.exists():
            continue
        try:
            analysis = analyze_am(read_samples(rtl_path), config_of(record))
        except Exception:
            continue
        for line in analysis.get("lines") or []:
            sheet.append([record["case"], line.get("label"),
                          line["expected_hz"] / 1e3, line["measured_bin_hz"] / 1e3,
                          clean(line.get("peak_amplitude")), clean(line.get("ratio_to_carrier")),
                          clean(line.get("ideal_ratio_to_carrier")),
                          f'=IF(AND(ISNUMBER(F{row}),ISNUMBER(G{row})),F{row}-G{row},"")'])
            for c, fmt in ((3, "#,##0.000"), (4, "#,##0.000"), (5, "0.00"), (6, "0.0000"), (7, "0.0000"), (8, "0.0000")):
                sheet.cell(row=row, column=c).number_format = fmt
            row += 1
    style_header(sheet)
    style_body(sheet, 2, row - 1, len(titles))
    note(sheet, row + 1, "Measured on the RTL output. Ideal ratio of each sideband to the carrier is mu/2; "
                         "finite word length and the window cause small differences.")
    for letter, width in zip("ABCDEFGH", (22, 16, 14, 16, 18, 14, 12, 12)):
        sheet.column_dimensions[letter].width = width
    sheet.freeze_panes = "C2"
    return sheet


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=ROOT / "results" / "results.xlsx")
    args = parser.parse_args()

    records = load_records()
    synth = load_synth()
    if not records and not synth:
        print("Nothing to report yet: run verify_rtl.py, check_result.py or the synthesis loop first.")
        return 2

    book = Workbook()
    sheet_summary(book, records)
    sheet_figures(book, records)
    sheet_spectrum(book, records)
    sheet_resources(book, synth)
    sheet_settings(book)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    book.save(args.out)

    regression = sum(r["source"] == "regression" for r in records)
    print(f"Cases     : {regression} regression, {len(records) - regression} custom, "
          f"{sum(r['status'] == 'PASS' for r in records)} PASS")
    print(f"Synthesis : {len(synth)} of 6 configurations")
    print(f"Written   : {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
