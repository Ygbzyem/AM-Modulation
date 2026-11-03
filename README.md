# AM Modulator (DSB-FC) — Verilog RTL Project

A fixed-point **amplitude modulator** in Verilog: two NCOs drive an envelope stage and a
multiplier to produce a DSB-FC AM signal. The design comes with a bit-exact Python golden model
and a full-cycle versus quarter-wave sine ROM comparison for resource analysis on an Artix-7.

| | |
|---|---|
| Design | 7 RTL modules, 12-bit signed datapath, 32-bit phase accumulators, 100 MHz clock |
| Target | Vivado, Artix-7 `xc7a35tcpg236-1` (no board needed) |
| Verification | **13 / 13** configurations match the golden model bit for bit, 10 000 samples each |
| ROM comparison | Full and quarter-wave ROMs produce identical output at AW = 8, 10, 12 |
| Latency | **3 clocks** from phase accumulator to `am_out` (2 ROM stages + 1 multiplier stage) |

## Block diagram

```
ftw_msg ─► NCO ─► msg ─┐
                       ├─► am_envelope ─► env ─┐
            amp_msg ───┘                       ├─► am_multiplier ─► am_out
            amp_car ───────────────────────────┘        ▲
ftw_car ─► NCO ─► car ──────────── (delay 1 clk) ───────┘

NCO = phase_acc (32 bit) + sine ROM, ROM architecture chosen by USE_QUARTER_ROM
```

The datapath is integer-only; the integer 2047 represents 1.0, so each product is shifted right by 11 bits:

```verilog
msg_term = (amp_msg * msg) >>> 11     // 12b x 12b = 25b -> 14b
env      = amp_car + msg_term         // 14b signed
am_out   = (env * car) >>> 11         // 14b x 12b = 26b -> 16b
```

The modulation index is not a separate signal: `μ = amp_msg / amp_car`. Setting `amp_car = 0`
gives DSB-SC with the same hardware.

## Repository layout

```
src/                 synthesizable RTL (phase_acc, sine_rom_full, sine_rom_quarter, nco,
                     am_envelope, am_multiplier, am_modulator_top)
tb/                  testbench
model/               integer golden model, sine table generator, comparison and spectrum analysis
mem/                 sine tables, one full and one quarter table per AW (design sources)
constraint/          clock constraint, 100 MHz
scripts/             run_experiments.py, sweep_impl.tcl, vivado_reports.py, write_excel.py,
                     make_report_assets.py, cases.yaml
tests/               unit tests
results/             results.xlsx, summary.json, verification_run.csv, figures/, rpt/
docs/                theory, Vivado flow, report (docs/report/main.tex) and shared figures
```

## Interface

`am_modulator_top`

| Port | Dir | Width | Meaning |
|---|---|---|---|
| `clk` | in | 1 | 100 MHz system clock |
| `rst` | in | 1 | synchronous, active high |
| `ftw_car` | in | 32 | carrier tuning word, `ftw = f × 2^32 / 100e6` |
| `ftw_msg` | in | 32 | message tuning word |
| `amp_car` | in | 12 | carrier amplitude, unsigned |
| `amp_msg` | in | 12 | message amplitude, unsigned |
| `am_out` | out | 16 | modulated output, signed |

Parameters: `AW` (ROM address bits: 8, 10, 12), `USE_QUARTER_ROM` (0 = full, 1 = quarter),
`FULL_MEM_FILE`, `QUARTER_MEM_FILE`. Default stimulus: `ftw_car = 42 949 673` (1 MHz),
`ftw_msg = 858 993` (20 kHz), `amp_car = 2000`, `amp_msg = 1000` (μ = 0.5).

## Reproducing the results

Requires Python 3.9+ and Vivado (`xvlog`, `xelab`, `xsim`, `vivado` in `PATH`). Keep the repository in a
path with ASCII characters only.

```bash
pip install -r scripts/requirements.txt
python model/gen_sine_rom.py                      # sine tables (already committed in mem/)
python scripts/run_experiments.py                 # simulate, compare, spectra, figures, results.xlsx
python scripts/run_experiments.py --impl          # also run synthesis and implementation (6 configurations)
python scripts/make_report_assets.py              # report figures and LaTeX tables
cd docs/report && latexmk -pdf main.tex
python -m unittest discover -s tests              # unit tests
```

`run_experiments.py` exits with 0 when all 13 cases pass. Details are in
[`docs/04-vivado-flow.md`](docs/04-vivado-flow.md); the theory is in [`docs/01-theory.md`](docs/01-theory.md).

## Verification summary

Each case is simulated, the first 3 warm-up samples are dropped, and the remaining 10 000 samples are compared
with the golden model sample by sample.

| Cases | Configuration | Result |
|---|---|---|
| 1–5 | AW = 8, full ROM, μ = 0 / 0.25 / 0.5 / 1.0 / 1.5 | PASS, 0 mismatches |
| 6 | DSB-SC (`amp_car = 0`) | PASS, 0 mismatches |
| 7 | message 100 kHz | PASS, 0 mismatches |
| 8–13 | AW = 8 / 10 / 12 × full / quarter, μ = 0.5 | PASS, 0 mismatches |

With the defaults the envelope runs from 1000 to 2999 and `am_out` from −2998 to 2997. The spectrum has three
lines at 980, 1000 and 1020 kHz. SFDR is 48.1, 60.7 and 71.9 dB for AW = 8, 10 and 12, the same for both ROM
architectures. Resource, timing and power numbers are in `results/results.xlsx`, with the Vivado reports in
`results/rpt/`.

## Limitations

- Simulation and synthesis only; the design has not been run on a board.
- The modulator is DSB-FC; there is no demodulator, and DSB-SC is the degenerate case `amp_car = 0`.
- The message is a single tone from the second NCO, not real audio.
- Phase truncation (32-bit accumulator addressing a 2^AW table) limits spectral purity.
- The constraint file defines the 10 ns clock and false paths on all ports, so Fmax reflects internal register-to-register paths.

## Future work

- Envelope detector for a full modulate–demodulate chain.
- Single-sideband modulation.
- AXI-Stream wrapper for a Zynq design.

## License

MIT — see [LICENSE](LICENSE).
