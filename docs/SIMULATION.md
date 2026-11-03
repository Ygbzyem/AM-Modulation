# How to simulate and synthesize this project

This guide is for anyone who has just cloned the repository. Everything runs from the Vivado GUI; Python is only
used afterwards to compare the RTL with the golden model and to build the results workbook.

| What | Where | Checked by |
|---|---|---|
| Live demo with waveforms, 7 self-checks | `tb_am_top` | the testbench itself |
| One configuration of your choice | `tb_am_top_filebased` + `tb/am_config.txt` | `golden_model/check_result.py` |
| All 18 regression cases | `tb_am_regression` | `golden_model/verify_rtl.py` |
| Resources and timing, 6 configurations | Tcl loop in [Section 7](#7-synthesis-of-all-six-configurations) | `golden_model/make_excel.py` |

## 1. Prerequisites

| Need | Notes |
|---|---|
| Vivado 2020.2 | XSIM for simulation, synthesis and implementation for `xc7a35tcpg236-1` |
| Python 3.8+ | `pip install -r requirements.txt` (numpy, matplotlib, openpyxl) |
| An **ASCII-only path** | Vivado cannot open files in folders with accents, e.g. `Tài liệu`. Clone into `C:\GitHub\AM-Modulation` or similar |

```bash
git clone https://github.com/Ygbzyem/AM-Modulation.git
cd AM-Modulation
pip install -r requirements.txt
python -m unittest discover -s tests        # 24 tests -> OK
```

## 2. One-time Vivado project setup

1. Create a project in `AM_Modulation_Vivado/` inside the repository, part `xc7a35tcpg236-1`.
2. **Design Sources:** add `src/*.v`, `constraint/constraints.xdc` and all six `mem/*.mem` files. Do **not** tick
   *Copy sources into project*, so the project always uses the files in the repository. Right-click
   `am_modulator_top` → *Set as Top*.
3. **Simulation Sources:** add `tb/tb_am_top.v`, `tb/tb_am_top_filebased.v` and `tb/tb_am_regression.v`. Do
   **not** add `tb/am_config.txt`: Vivado would copy it into the run folder and the copy would go stale when
   you edit the original.
4. *Settings → Simulation → Simulation*: set `xsim.simulate.runtime` to `all` and tick
   `xsim.simulate.log_all_signals`.

The Vivado project folder is not committed (see `.gitignore`), so every team member does this once.

Check that synthesis finds the tables: after *Run Synthesis*,

```
findstr /C:"CRITICAL WARNING" AM_Modulation_Vivado\AM_Modulation_Vivado.runs\synth_1\runme.log
```

must print nothing. `could not open $readmem data file` means the `.mem` files are missing from Design Sources.

## 3. Demo: `tb_am_top`

Right-click `tb_am_top` → *Set as Top*, then *Run Behavioral Simulation*. The Tcl console ends with:

```
[PASS] am_out is 0 while reset is asserted
[PASS] no X/Z on am_out after the pipeline fills
[PASS] bit-exact against the integer reference model
[PASS] envelope peak ~ (amp_car + amp_msg) * 2047/2048
[PASS] envelope trough ~ (amp_car - amp_msg) * 2047/2048
[PASS] envelope never crosses zero (mu <= 1)
       measured mu = 0.5000, expected 0.5000
[PASS] measured modulation index within 0.01 of amp_msg/amp_car
RESULT: 7/7 PASS (0 skipped)
```

To try another setting, edit the `localparam` block at the top of `tb/tb_am_top.v` (`AW`, `USE_QUARTER_ROM`,
the two `MEM_FILE` names, `FTW_CAR`, `FTW_MSG`, `AMP_CAR`, `AMP_MSG`) and run again.

### Waveforms in analog style

`tb/tb_am_top_behav.wcfg` opens with the demo layout. To build it yourself:

1. In the **Scope** window select `u_dut`; drag `msg`, `car` and `am_out` from **Objects** into the waveform.
   Select `u_dut → u_env` and drag `env`.
2. For each signal: right-click → **Radix → Signed Decimal** first, then **Waveform Style → Analog**.
3. **Waveform Style → Analog Settings**: Row Height about 200, **Y Range Auto**, Interpolation Linear. With the
   default Y range a 16-bit signal is scaled to ±32768 and `am_out` (±3000) looks almost flat.
4. **Zoom Fit**, then *File → Simulation Waveform → Save Configuration As* `tb/tb_am_top_behav.wcfg`.

A signal added after the run is empty unless `log_all_signals` is on; otherwise click **Restart** and **Run All**.

## 4. Any configuration: `tb_am_top_filebased`

Edit `tb/am_config.txt`, save, set `tb_am_top_filebased` as top and run:

```text
CASE    = fc2M_fm50k_mu075      # unique name, the same name overwrites the earlier run
FC_HZ   = 2000000               # or FTW_CAR = <tuning word>
FM_HZ   = 50000                 # or FTW_MSG = <tuning word>
AMP_CAR = 2000                  # 0 .. 4095
AMP_MSG = 1500                  # 0 .. 4095, mu = AMP_MSG / AMP_CAR
SAMPLES = 10000                 # 10 000 samples = 100 us at 100 MHz
```

The console shows what the RTL actually received:

```
Config read from ../../../../../tb/am_config.txt
case fc2M_fm50k_mu075: AW=8 ROM=FULL
  FTW_CAR = 85899346  (2000000.0 Hz)
  FTW_MSG = 2147484  (50000.0 Hz)
  AMP_CAR = 2000, AMP_MSG = 1500, SAMPLES = 10000
```

Then compare and store the run:

```bash
python golden_model/check_result.py
```

It reads the header line of `am_out.txt`, rebuilds the golden reference with the same configuration, compares
sample by sample and writes `results/custom/<CASE>/` (samples, two figures, `record.json`).

`AW` and the ROM type change the hardware, so they are set as generics before the run:

```tcl
set_property generic {AW=10 USE_QUARTER_ROM=1 FULL_MEM_FILE="sine_full_AW10.mem" QUARTER_MEM_FILE="sine_quarter_AW10.mem"} [get_filesets sim_1]
```

and cleared afterwards with `set_property generic {} [get_filesets sim_1]`.

Limits: amplitudes above 4095 are truncated (the testbench warns), keep `FC_HZ` at or below about 10 MHz for a
readable waveform, and raise `SAMPLES` for low `FM_HZ` (5 kHz needs 40 000 samples for two periods).

## 5. Regression: `tb_am_regression`

Set `tb_am_regression` as top and run. It writes `rtl_case01.txt` ... `rtl_case18.txt` into the XSIM run folder
in about 1.3 ms of simulated time. The console lists the ROM cases (08–13) first because their six DUTs run in
parallel, then the functional cases (01–07) and the edge cases (14–18).

```bash
python golden_model/verify_rtl.py
```

Expected: `18/18 PASS, 0 FAIL, 0 missing`, with figures and `RTL_VERIFICATION.md` in `results/rtl/`.

## 6. Test cases

| # | Case | Parameters that differ from the default | What to look for |
|---:|---|---|---|
| 1 | `functional_mu_0` | `AMP_MSG = 0` | constant-amplitude carrier |
| 2 | `functional_mu_0.25` | `AMP_MSG = 500` | shallow envelope |
| 3 | `functional_mu_0.5` | default | the reference case |
| 4 | `functional_mu_1` | `AMP_MSG = 2000` | envelope touches zero once per period |
| 5 | `functional_mu_1.5` | `AMP_MSG = 3000` | overmodulation, carrier phase reverses |
| 6 | `functional_dsb_sc` | `AMP_CAR = 0` | suppressed carrier |
| 7 | `functional_fm_100k` | `FM_HZ = 100000` | ten envelope periods in 100 µs |
| 8–13 | `rom_aw{8,10,12}_{full,quarter}` | generics | full and quarter identical, finer steps at larger AW |
| 14 | `edge_amp_max` | `AMP_CAR = AMP_MSG = 4095` | largest output, no overflow |
| 15 | `edge_dsb_max` | `AMP_CAR = 0`, `AMP_MSG = 4095` | most negative envelope |
| 16 | `edge_ftw_nyquist` | `FC_HZ = 50000000` | ±36 output, Nyquist limit |
| 17 | `edge_ftw_max` | `FTW_CAR = 4294967295` | frozen negative carrier |
| 18 | `edge_ftw_zero` | `FC_HZ = 0` | `am_out` traces the envelope |

Default: `FC_HZ = 1000000`, `FM_HZ = 20000`, `AMP_CAR = 2000`, `AMP_MSG = 1000`, AW = 8, full ROM.

## 7. Synthesis of all six configurations

Paste in the Tcl console of the open project. Use this block as is: in Tcl a `#` comment is only valid at the
start of a command (`;#` after one), and non-ASCII characters are not allowed.

```tcl
set root C:/GitHub/AM-Modulation
set_property top am_modulator_top [get_filesets sources_1]
foreach aw {8 10 12} {
  foreach q {0 1} {
    set tag aw${aw}_[expr {$q ? "quarter" : "full"}]
    puts "==== $tag ===="
    set_property generic "AW=$aw USE_QUARTER_ROM=$q FULL_MEM_FILE=\"sine_full_AW${aw}.mem\" QUARTER_MEM_FILE=\"sine_quarter_AW${aw}.mem\"" [get_filesets sources_1]
    reset_run synth_1
    reset_run impl_1
    launch_runs impl_1 -jobs 2
    wait_on_run impl_1
    open_run impl_1
    file mkdir $root/results/synth/$tag
    report_utilization    -file $root/results/synth/$tag/utilization.rpt
    report_timing_summary -file $root/results/synth/$tag/timing.rpt
    report_power          -file $root/results/synth/$tag/power.rpt
    close_design
  }
}
set_property generic {} [get_filesets sources_1]
puts "All 6 configurations done."
```

It takes 15–30 minutes; do not click in the GUI until the last line appears. Check that the reports belong to the
whole design:

```
findstr /C:"Design       :" results\synth\aw8_full\utilization.rpt
```

must print `am_modulator_top`. A report of `nco` means the synthesis top was wrong.

## 8. Results workbook

```bash
python golden_model/make_excel.py
```

collects `results/rtl/`, `results/custom/` and `results/synth/` into `results/results.xlsx` (sheets Summary,
Figures, Spectrum, Resources, Settings). It can be run at any stage and skips synthesis reports whose top is not
`am_modulator_top`.

## 9. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `am_out` is X, or every sample fails from 0 | `.mem` files not found | Add `mem/*.mem` to Design Sources ([Section 2](#2-one-time-vivado-project-setup)) |
| `could not open $readmem data file 'model/mem/...'` | old copy of the sources in the project | Remove the `.v` files from the project and add them again from `src/` without copying |
| `rtl_case*.txt` missing or short | runtime stopped at 1000 ns | `xsim.simulate.runtime = all` |
| `am_config.txt not found` | project not inside the repository | keep the project at `AM_Modulation_Vivado/` |
| Plusargs still override the config file | leftover `xsim.more_options` | `set_property -name xsim.simulate.xsim.more_options -value {} -objects [get_filesets sim_1]` |
| Timing summary shows WNS = NA | logic removed, usually the ROM was empty | check for `Synth 8-4445` in `runme.log` |
| Tcl: `wrong # args: should be "set varName ?newValue?"` | a `#` comment after a command | remove it or use `;#` |
| Report says `Design : nco` | wrong synthesis top | *Set as Top* on `am_modulator_top` |
