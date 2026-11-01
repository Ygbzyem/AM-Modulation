# AM Modulator (DSB-FC) — Verilog RTL Project

A fixed-point **amplitude modulator** in Verilog: two NCOs drive an envelope stage and a
multiplier to produce a DSB-FC AM signal. The design ships with a bit-exact Python golden
model, two testbenches, and a full/quarter-wave sine ROM comparison for resource analysis.

| | |
|---|---|
| Design | 7 RTL modules, 12-bit signed datapath, 32-bit phase accumulators, 100 MHz clock |
| Self-checking testbench | **7 / 7** checks pass, see [Section 8.1](#81-self-checking-testbench) |
| Golden model | **13 / 13** configurations match bit-for-bit, 10 000 samples each, see [Section 8.2](#82-golden-model-rtl-vs-python-reference) |
| ROM comparison | Full and quarter-wave ROMs are **bit-identical** at AW = 8, 10, 12 |
| Latency | **3 clocks** from input to `am_out` (2 ROM stages + 1 multiplier stage) |
| Synthesis | Vivado, Artix-7 `xc7a35tcpg236-1` — *pending, see [Section 9](#9-synthesis-results)* |

---

## Table of Contents

1. [Quick Start](#1-quick-start)
2. [System Overview](#2-system-overview)
3. [Block Diagram](#3-block-diagram)
4. [Repository Structure](#4-repository-structure)
5. [Module Index](#5-module-index)
6. [Fixed-Point Contract](#6-fixed-point-contract)
7. [Interface Specifications](#7-interface-specifications)
8. [Verification](#8-verification)
9. [Synthesis Results](#9-synthesis-results)
10. [Limitations](#10-limitations)
11. [Future Work](#11-future-work)
12. [License](#12-license)

---

## 1. Quick Start

```bash
git clone https://github.com/Ygbzyem/AM-Modulation.git
cd AM-Modulation
```

You need **Python 3.8+** and **one** simulator: Icarus Verilog (`iverilog`, `vvp`) or
Vivado (XSIM). If you simulate with Vivado, keep the project in a folder whose path
contains only ASCII characters — no accents, no Vietnamese diacritics.

```bash
python scripts/run_tests.py                        # self-checking testbench -> 7/7 PASS
python golden_model/run_verification.py            # RTL vs golden model -> PASS
python golden_model/run_verification.py --all      # all 13 configurations -> 13/13 PASS
```

Add `--sim xsim` to either command to use Vivado XSIM instead of Icarus.
The full walkthrough, including the Vivado GUI flow and the expected console output, is in
**[docs/SIMULATION.md](docs/SIMULATION.md)**.

---

## 2. System Overview

Amplitude modulation makes the amplitude of a fast **carrier** follow a slow **message**.
The line joining the peaks — the *envelope* — has the shape of the message, so a receiver
recovers the message by tracking that envelope.

```
s(t) = A_c · [1 + μ · m(t)] · cos(2π · f_c · t)
```

In this design the textbook formula becomes three integer operations, executed every clock:

```verilog
msg_term = (amp_msg * msg) >>> 11     // scale the message
env      = amp_car + msg_term         // lift it above zero  (the "1 +" term)
am_out   = (env * car) >>> 11         // multiply by the carrier
```

The modulation index is **not a separate signal**: `μ = amp_msg / amp_car`. Keeping
`amp_msg ≤ amp_car` guarantees `env > 0`, so the envelope never folds. Setting
`amp_car = 0` removes the carrier term entirely and the design produces **DSB-SC**
instead — the same hardware, a different input value.

Both sine waves come from NCOs (numerically controlled oscillators): a 32-bit phase
accumulator adds a tuning word every clock, and the top `AW` bits address a sine lookup
table. Output frequency is `f_out = FTW × f_clk / 2^32`, giving 0.023 Hz resolution at
100 MHz. Both NCOs share the same table; only their tuning words differ.

---

## 3. Block Diagram

```
ftw_msg ─► NCO ─► msg ─┐
                       ├─► am_envelope ─► env ─┐
            amp_msg ───┘                       ├─► am_multiplier ─► am_out
            amp_car ───────────────────────────┘        ▲
ftw_car ─► NCO ─► car ──────────── (delay 1 clk) ───────┘
```

*The carrier is delayed by one clock inside `am_modulator_top` so that it reaches the
multiplier in the same cycle as the envelope, which costs one register stage.*

---

## 4. Repository Structure

```
.
├── src/                          # synthesizable RTL
│   ├── phase_acc.v               #   32-bit phase accumulator (shared by both NCOs)
│   ├── sine_rom_full.v           #   full-period sine table, 2^AW entries
│   ├── sine_rom_quarter.v        #   quarter-wave table, 2^(AW-2) entries + fold logic
│   ├── nco.v                     #   phase_acc + ROM, architecture chosen by parameter
│   ├── am_envelope.v             #   amp_car + (amp_msg * msg >>> 11)
│   ├── am_multiplier.v           #   (env * car) >>> 11
│   └── am_modulator_top.v        #   top level: 2 NCOs + envelope + multiplier
├── tb/                           # testbenches
│   ├── tb_am_top.v               #   self-checking, parameters hard-coded in the file
│   └── tb_am_top_filebased.v     #   parameters from the command line, writes a sample file
├── golden_model/                 # Python reference model and automatic comparison
│   ├── run_verification.py       #   simulate + compare in one command
│   ├── am_golden.py              #   integer-exact reference datapath
│   ├── gen_sine_rom.py           #   builds every .mem table, asserts quarter == full
│   ├── compare.py                #   strict sample-by-sample comparison
│   ├── spectrum.py, plot_txt.py  #   FFT analysis and plots
│   └── verification_logs/        #   golden/RTL sample files from the latest run
├── mem/                          # sine tables (design sources, committed)
│   ├── sine_full_AW{8,10,12}.mem
│   ├── sine_quarter_AW{8,10,12}.mem
│   └── manifest.json             #   formula, entry counts, SHA-256 of every table
├── tests/test_part_a.py          # unit tests for the Python model (21 tests)
├── scripts/
│   ├── run_tests.py              #   runs the self-checking testbench
│   └── synth.tcl                 #   Vivado batch sweep: 3 table sizes x 2 architectures
├── constraint/constraints.xdc    # 100 MHz clock constraint
├── docs/SIMULATION.md            # how to run everything, step by step
├── image/                        # block diagrams and waveforms
└── results/                      # synthesis reports and summary.csv
```

---

## 5. Module Index

| Module | Function | Key parameters |
|---|---|---|
| `phase_acc` | free-running phase accumulator, wraps naturally on overflow | `PW = 32` |
| `sine_rom_full` | direct lookup, two registered stages | `AW`, `DW`, `MEM_FILE` |
| `sine_rom_quarter` | folds address and sign to cover a full period from a quarter table | `AW`, `DW`, `MEM_FILE` |
| `nco` | combines accumulator and ROM; `generate` selects the architecture | `USE_QUARTER_ROM` |
| `am_envelope` | signed x unsigned multiply, shift, offset | `DW`, `EW = DW+2` |
| `am_multiplier` | final product and output scaling | `DW`, `EW`, `OW = 16` |
| `am_modulator_top` | instantiates everything, aligns the carrier | all of the above |

Both ROM modules expose the same port list, so `nco.v` swaps them without any other change.
That is what makes the resource comparison in Section 9 a fair one: only the ROM differs.

---

## 6. Fixed-Point Contract

The datapath is integer-only. The integer **2047 represents 1.0**, so every product is
scaled by 2048 and has to be shifted right by 11 bits to return to the original scale.

| Stage | Expression | Width |
|---|---|---|
| ROM sample | `car`, `msg` | 12-bit signed, −2048 … 2047 |
| Message scaling | `(amp_msg * msg) >>> 11` | 25-bit product, kept as 14 bits |
| Envelope | `amp_car + msg_term` | 14-bit signed |
| Output | `(env * car) >>> 11` | 26-bit product, kept as 16 bits |

Two details the golden model must reproduce exactly:

- `>>>` **truncates toward negative infinity**, it does not round. Python's `>>` behaves
  identically for signed integers, which is why the reference model uses it.
- `amp_msg` is unsigned and `msg` is signed. The RTL widens the unsigned operand with a
  leading zero — `$signed({1'b0, amp_msg})` — before multiplying. Without that cast the
  negative half of every message cycle comes out wrong while the waveform still *looks*
  plausible.

With the default settings (`amp_car = 2000`, `amp_msg = 1000`, i.e. μ = 0.5) the envelope
runs from **1000 to 2999** and `am_out` from **−2998 to 2997**. These numbers are a fast
sanity check after any change.

---

## 7. Interface Specifications

`am_modulator_top`

| Port | Dir | Width | Meaning |
|---|---|---|---|
| `clk` | in | 1 | 100 MHz system clock |
| `rst` | in | 1 | synchronous, active high |
| `ftw_car` | in | 32 | carrier tuning word; `ftw = f × 2^32 / 100e6` |
| `ftw_msg` | in | 32 | message tuning word |
| `amp_car` | in | 12 | carrier amplitude, unsigned |
| `amp_msg` | in | 12 | message amplitude, unsigned; `μ = amp_msg / amp_car` |
| `am_out` | out | 16 | modulated output, signed |

Default stimulus: `ftw_car = 42_949_673` (1 MHz), `ftw_msg = 858_993` (20 kHz),
`amp_car = 2000`, `amp_msg = 1000`.

---

## 8. Verification

### 8.1 Self-checking testbench

`techbench/tb_am_top.v` holds its parameters in the file and checks the design against
properties derived from theory, not against a stored vector file:

```
[PASS] reset dua am_out ve 0
[PASS] bien do duong dung ky vong (2997)
[PASS] bien do am dung ky vong (-2998)
[PASS] dinh duong bao ~2999 (amp_car + amp_msg)
[PASS] day duong bao ~1000 (amp_car - amp_msg)
[PASS] duong bao khong cham 0, tuc mu <= 1
[PASS] chi so dieu che do duoc ~0,50
KET QUA: 7/7 PASS
```

The last check measures the envelope peaks from the waveform and recomputes
`μ = (Emax − Emin) / (Emax + Emin)`, which must come back as 0.50.

### 8.2 Golden model: RTL vs Python reference

`techbench/tb_am_top_filebased.v` takes every stimulus value from the command line, so one
testbench covers every configuration. `golden_model/run_verification.py` drives it, runs the
Python reference with the same settings, and compares the two streams **sample by sample**.
The RTL is given 3 extra samples and the first 3 are dropped, which is the pipeline latency.

```
case              ket qua       so mau      lech
mu_0              PASS           10000         0
mu_0.25           PASS           10000         0
mu_0.5            PASS           10000         0
mu_1              PASS           10000         0
mu_1.5            PASS           10000         0
dsb_sc            PASS           10000         0
fm_100k           PASS           10000         0
aw8_full          PASS           10000         0
aw8_quarter       PASS           10000         0
aw10_full         PASS           10000         0
aw10_quarter      PASS           10000         0
aw12_full         PASS           10000         0
aw12_quarter      PASS           10000         0
TAT CA PASS
```

Cases 1–7 cover the functional range: no modulation, normal modulation, the μ = 1 limit,
over-modulation, suppressed carrier, and a wider message bandwidth. Cases 8–13 are the
resource experiment: the full and quarter-wave ROMs produce **identical** output at every
table size, so the memory saving in Section 9 costs nothing in signal quality.

### 8.3 Python unit tests

```bash
python -m unittest discover -s tests
# Ran 21 tests ... OK
```

`gen_sine_rom.py` additionally asserts, at every address and every table size, that the
quarter-wave reconstruction equals the direct full table. The tables are generated with the
midpoint formula `round(2047 · sin(2π(n + 0.5)/2^AW))`; the `+ 0.5` is what makes that
symmetry exact.

---

## 9. Synthesis Results

*To be filled in by `vivado -mode batch -source scripts/synth.tcl`. The sweep writes three
reports per configuration into `results/<AW><ARCH>/` and one summary row into
`results/summary.csv`.*

| AW | ROM | LUT | FF | LUTRAM/BRAM | DSP | WNS (ns) | Fmax (MHz) |
|---|---|---|---|---|---|---|---|
| 8 | full | | | | | | |
| 8 | quarter | | | | | | |
| 10 | full | | | | | | |
| 10 | quarter | | | | | | |
| 12 | full | | | | | | |
| 12 | quarter | | | | | | |

Hypotheses under test:

- **H1** — both architectures produce identical samples. *Confirmed in simulation
  (Section 8.2) at AW = 8, 10 and 12.*
- **H2** — the quarter-wave table uses about 75 % less memory but adds fold logic, so the
  LUT count may not drop at small table sizes.
- **H3** — Fmax may fall slightly for the quarter-wave ROM because of the extra negation.

---

## 10. Limitations

- Simulation and synthesis only; the design has not been run on a board.
- The modulator is DSB-FC. There is no demodulator, and DSB-SC is reachable only as the
  degenerate case `amp_car = 0`.
- The message is a single tone generated internally by the second NCO, not real audio.
- Phase truncation (32-bit accumulator addressing a 2^AW table) limits spectral purity;
  `golden_model/spectrum.py` measures the resulting SFDR.

---

## 11. Future Work

- Fill in Section 9 and discuss the memory-versus-logic trade-off.
- Add an envelope detector so a full modulate–demodulate chain can be shown.
- Single-sideband modulation, which halves the occupied bandwidth.
- An AXI-Stream wrapper so the block can be dropped into a Zynq design.

---

## 12. License

MIT — see [LICENSE](LICENSE).
