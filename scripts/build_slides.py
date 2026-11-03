"""Build docs/slides/AM_Modulator.pptx from results/summary.json and the figures."""
from __future__ import annotations

import json
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
NAVY, GREY = RGBColor(0x1F, 0x3A, 0x5F), RGBColor(0x44, 0x44, 0x44)
rows = {r["case_id"]: r for r in json.loads((ROOT / "results/summary.json").read_text())}

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
blank = prs.slide_layouts[6]


def text(slide, x, y, w, h, content, size=20, bold=False, color=GREY):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.word_wrap = True
    lines = content if isinstance(content, list) else [content]
    for i, line in enumerate(lines):
        p = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
        p.text = line
        p.font.size, p.font.bold, p.font.color.rgb = Pt(size), bold, color
        p.space_after = Pt(8)
    return box


def slide(title, bullets=None, image=None, image_w=12.0, size=22):
    s = prs.slides.add_slide(blank)
    text(s, 0.6, 0.35, 12, 0.9, title, 32, True, NAVY)
    if bullets and image:
        text(s, 0.6, 1.4, 5.0, 5.5, ["• " + b for b in bullets], size)
        pic = s.shapes.add_picture(str(ROOT / image), Inches(5.8), Inches(1.4), width=Inches(7.2))
        if pic.height > Inches(5.8):
            ratio = Inches(5.8) / pic.height
            pic.height, pic.width = Inches(5.8), int(pic.width * ratio)
    elif bullets:
        text(s, 0.6, 1.4, 12, 5.5, ["• " + b for b in bullets], size)
    elif image:
        pic = s.shapes.add_picture(str(ROOT / image), Inches(0.6), Inches(1.4), width=Inches(image_w))
        if pic.height > Inches(5.8):
            ratio = Inches(5.8) / pic.height
            pic.height, pic.width = Inches(5.8), int(pic.width * ratio)
    return s


def table(s, header, data, x=0.6, y=1.5, w=12.1, size=14):
    shape = s.shapes.add_table(len(data) + 1, len(header), Inches(x), Inches(y), Inches(w), Inches(0.4 * (len(data) + 1)))
    t = shape.table
    for j, h in enumerate(header):
        t.cell(0, j).text = h
    for i, r in enumerate(data, 1):
        for j, v in enumerate(r):
            t.cell(i, j).text = str(v)
    for row in t.rows:
        for cell in row.cells:
            for p in cell.text_frame.paragraphs:
                p.font.size = Pt(size)


def fmt(v, spec="{}"):
    return "—" if v is None or v != v else spec.format(v)


s = prs.slides.add_slide(blank)
text(s, 0.8, 2.3, 11.5, 1.5, "AM Modulator (DSB-FC) on FPGA", 44, True, NAVY)
text(s, 0.8, 3.7, 11.5, 1.5, ["RTL design project — full-cycle vs quarter-wave sine ROM",
                              "Artix-7 xc7a35tcpg236-1, 100 MHz"], 22)

slide("Problem and goal", [
    "Build an amplitude modulator in fixed-point Verilog: s(t) = Ac [1 + μ m(t)] cos(2π fc t)",
    "Verify it bit for bit against an integer Python golden model",
    "Compare two sine-ROM architectures: full 2^AW words vs quarter-wave 2^(AW−2) words",
    "Measure LUT, FF, LUTRAM, BRAM, DSP, WNS, Fmax, power and SFDR for AW = 8, 10, 12",
])
slide("Signal model", [
    "μ = amp_msg / amp_car; μ > 1 is overmodulation (envelope goes negative)",
    "Three spectral lines at fc − fm, fc, fc + fm = 980 / 1000 / 1020 kHz",
    "Bandwidth = 2 fm; sideband-to-carrier ratio = μ / 2",
    "amp_car = 0 gives DSB-SC with the same hardware",
])
slide("Architecture", image="docs/figures/block_diagram.png", image_w=12.0)
slide("Fixed-point contract", [
    "Integer 2047 represents 1.0, so every product is shifted right by 11 bits",
    "msg_term = (amp_msg · msg) >>> 11  (25 b → 14 b)",
    "env = amp_car + msg_term  (14 b signed)",
    "am_out = (env · car) >>> 11  (26 b → 16 b)",
    "Latency: 3 clocks (two ROM stages + one multiplier stage)",
])
slide("NCO and sine ROM", [
    "32-bit phase accumulator, f = FTW · fclk / 2^32 (0.023 Hz resolution)",
    "ftw_car = 42 949 673 (1 MHz), ftw_msg = 858 993 (20 kHz)",
    "Full ROM: 2^AW words. Quarter-wave ROM: 2^(AW−2) words, −75 % memory",
    "Phase truncation to AW bits limits SFDR to about 6 dB per address bit",
])
slide("Verification method", [
    "Simulation of 10 000 samples per case; first 3 warm-up samples dropped",
    "Golden model uses the same integer arithmetic; comparison is sample by sample",
    "13 cases: 7 functional (μ sweep, DSB-SC, fm = 100 kHz) and 6 ROM configurations",
    "Unit tests: 30 passing",
])
fn = [(c, rows[c]) for c in rows if rows[c]["group"] == "functional"]
s = slide("Functional results")
table(s, ["Case", "Result", "Mismatches", "Envelope", "am_out range", "SFDR (dB)"],
      [(c, r["result"], r["mismatch_count"], f'{r["env_min"]}…{r["env_max"]}',
        f'{r["out_min"]}…{r["out_max"]}', fmt(r["sfdr_db"], "{:.1f}")) for c, r in fn])
slide("Waveforms and spectra", image="docs/figures/waveforms_spectra.png", image_w=12.0)
slide("Spectrum check (μ = 0.5)", [
    "Lines at 980, 1000, 1020 kHz with zero frequency error at the 10 kHz bin",
    "Sideband-to-carrier ratio matches μ/2 within 1.9·10⁻⁴",
    "Largest spurs lie at 45, 25 and 3 MHz (phase truncation images)",
], image="results/figures/functional_mu_0.5_spectrum.png")
rom = [(c, r) for c, r in rows.items() if r["group"] == "resource"]
s = slide("ROM comparison: results")
table(s, ["Case", "SFDR (dB)", "Result", "LUT", "FF", "LUTRAM", "BRAM", "WNS (ns)", "Fmax (MHz)"],
      [(c, fmt(r["sfdr_db"], "{:.1f}"), r["result"], fmt(r["lut"]), fmt(r["ff"]), fmt(r["lutram"]),
        fmt(r["bram"]), fmt(r["wns"], "{:.3f}"), fmt(r["fmax_mhz"], "{:.0f}")) for c, r in rom], size=13)
slide("SFDR and memory", image="docs/figures/sfdr_and_memory.png", image_w=12.0)
slide("Hypotheses", [
    "H1: full and quarter ROM give identical output — confirmed, 0 mismatches at AW = 8, 10, 12",
    "H2: quarter-wave cuts memory by 75 %; LUT count may not drop at small AW — see resource table",
    "H3: Fmax may drop slightly because of the address folding logic — see resource table",
])
slide("Conclusion", [
    "All 13 configurations match the golden model bit for bit",
    "SFDR follows the address width: 48.1 / 60.7 / 71.9 dB for AW = 8 / 10 / 12",
    "Quarter-wave ROM keeps the output identical while storing a quarter of the words",
    "Future work: envelope detector, single-sideband, AXI-Stream wrapper",
])

out = ROOT / "docs/slides/AM_Modulator.pptx"
out.parent.mkdir(parents=True, exist_ok=True)
prs.save(out)
print(out, len(prs.slides), "slides")
