r"""One command: simulate the RTL, then compare against the Python golden model.

    python golden_model/run_verification.py                  # default configuration, full ROM
    python golden_model/run_verification.py --rom quarter    # quarter-wave ROM architecture
    python golden_model/run_verification.py --aw 10          # 1024-entry table
    python golden_model/run_verification.py --amp-msg 3000   # over-modulation
    python golden_model/run_verification.py --all            # run all 13 configurations
    python golden_model/run_verification.py --sim xsim       # use Vivado XSIM instead of Icarus
    python golden_model/run_verification.py --no-sim         # compare existing files only

Works from any directory. Exit code: 0 = PASS, 1 = FAIL, 2 = tool problem.

RTL latency is 3 clocks (2 ROM stages + 1 multiplier stage), so the RTL runs
3 extra samples and the script drops the first 3 before comparing. That number
is documented in the README and in docs/SIMULATION.md.
"""

import argparse
import subprocess
import sys
from pathlib import Path
from shutil import which

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = ROOT / "src"
TB = ROOT / "techbench" / "tb_am_top_filebased.v"
TB_TOP = "tb_am_top_filebased"
SIM_DIR = ROOT / "sim"
LOG_DIR = HERE / "verification_logs"
LATENCY = 3          # 2 ROM stages + 1 multiplier stage

sys.path.insert(0, str(HERE))
from am_golden import Config, generate          # noqa: E402
from compare import compare                     # noqa: E402
from gen_sine_rom import generate_all           # noqa: E402


def mem_files(aw):
    return (f"mem/sine_full_AW{aw}.mem", f"mem/sine_quarter_AW{aw}.mem")


def cases(args):
    """Configurations to run."""
    if not args.all:
        return [("manual", Config(aw=args.aw, amp_car=args.amp_car, amp_msg=args.amp_msg,
                                  ftw_car=args.ftw_car, ftw_msg=args.ftw_msg,
                                  samples=args.samples,
                                  rom_arch=args.rom.upper()))]
    result = []
    for amp in (0, 500, 1000, 2000, 3000):
        result.append((f"mu_{amp / 2000:g}", Config(amp_msg=amp)))
    result.append(("dsb_sc", Config(amp_car=0, amp_msg=2000)))
    result.append(("fm_100k", Config(ftw_msg=4_294_967)))
    for aw in (8, 10, 12):
        for arch in ("FULL", "QUARTER"):
            result.append((f"aw{aw}_{arch.lower()}", Config(aw=aw, rom_arch=arch)))
    return result


def find_tool(name):
    found = which(name)
    if found:
        return found
    for base in (r"C:\iverilog\bin", r"C:\Program Files\iverilog\bin", "/usr/bin", "/usr/local/bin"):
        candidate = Path(base) / (name + (".exe" if sys.platform == "win32" else ""))
        if candidate.exists():
            return str(candidate)
    return None


def run_iverilog(cfg, out_path, tag):
    iverilog, vvp = find_tool("iverilog"), find_tool("vvp")
    if not (iverilog and vvp):
        print("iverilog/vvp not found. Install Icarus Verilog or use --sim xsim.")
        return 2
    SIM_DIR.mkdir(exist_ok=True)
    snapshot = SIM_DIR / f"tb_{tag}"
    full, quarter = mem_files(cfg.aw)
    build = [iverilog, "-g2005",
             f"-P{TB_TOP}.AW={cfg.aw}",
             f"-P{TB_TOP}.USE_QUARTER_ROM={1 if cfg.rom_arch == 'QUARTER' else 0}",
             f'-P{TB_TOP}.MEM_FULL="{full}"',
             f'-P{TB_TOP}.MEM_QUARTER="{quarter}"',
             "-o", str(snapshot)] + sorted(str(p) for p in SRC.glob("*.v")) + [str(TB)]
    if subprocess.run(build, cwd=ROOT).returncode:
        return 2
    run = [vvp, str(snapshot),
           f"+FTW_CAR={cfg.ftw_car}", f"+FTW_MSG={cfg.ftw_msg}",
           f"+AMP_CAR={cfg.amp_car}", f"+AMP_MSG={cfg.amp_msg}",
           f"+SAMPLES={cfg.samples + LATENCY}", f"+OUTFILE={out_path.relative_to(ROOT)}"]
    return 0 if subprocess.run(run, cwd=ROOT).returncode == 0 else 2


def run_xsim(cfg, out_path, tag):
    xvlog, xelab, xsim = find_tool("xvlog"), find_tool("xelab"), find_tool("xsim")
    if not (xvlog and xelab and xsim):
        print("xvlog/xelab/xsim not found. Open a Vivado shell or use --sim iverilog.")
        return 2
    full, quarter = mem_files(cfg.aw)
    sources = sorted(str(p.relative_to(ROOT)) for p in SRC.glob("*.v")) + [str(TB.relative_to(ROOT))]
    if subprocess.run([xvlog] + sources, cwd=ROOT).returncode:
        return 2
    elab = [xelab, "-debug", "typical", TB_TOP, "-s", f"snap_{tag}",
            "-generic_top", f"AW={cfg.aw}",
            "-generic_top", f"USE_QUARTER_ROM={1 if cfg.rom_arch == 'QUARTER' else 0}",
            "-generic_top", f"MEM_FULL={full}",
            "-generic_top", f"MEM_QUARTER={quarter}"]
    if subprocess.run(elab, cwd=ROOT).returncode:
        return 2
    run = [xsim, f"snap_{tag}", "-R",
           "-testplusarg", f"FTW_CAR={cfg.ftw_car}", "-testplusarg", f"FTW_MSG={cfg.ftw_msg}",
           "-testplusarg", f"AMP_CAR={cfg.amp_car}", "-testplusarg", f"AMP_MSG={cfg.amp_msg}",
           "-testplusarg", f"SAMPLES={cfg.samples + LATENCY}",
           "-testplusarg", f"OUTFILE={out_path.relative_to(ROOT)}"]
    return 0 if subprocess.run(run, cwd=ROOT).returncode == 0 else 2


def one_case(tag, cfg, args):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    golden_path = LOG_DIR / f"golden_{tag}.txt"
    rtl_path = LOG_DIR / f"rtl_{tag}.txt"

    rows = generate(cfg)
    golden_path.write_text("\n".join(str(r["out"]) for r in rows) + "\n", encoding="ascii")

    if not args.no_sim:
        status = (run_xsim if args.sim == "xsim" else run_iverilog)(cfg, rtl_path, tag)
        if status:
            return status, None
    if not rtl_path.exists():
        print(f"{rtl_path} is missing. Drop --no-sim or run the simulation first.")
        return 2, None

    result = compare(str(golden_path), str(rtl_path),
                     skip_rtl=LATENCY, expected_samples=cfg.samples)
    return (0 if result["passed"] else 1), result


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sim", choices=("iverilog", "xsim"), default="iverilog")
    parser.add_argument("--rom", choices=("full", "quarter"), default="full")
    parser.add_argument("--aw", type=int, default=8)
    parser.add_argument("--amp-car", type=int, default=2000)
    parser.add_argument("--amp-msg", type=int, default=1000)
    parser.add_argument("--ftw-car", type=int, default=42_949_673)
    parser.add_argument("--ftw-msg", type=int, default=858_993)
    parser.add_argument("--samples", type=int, default=10_000)
    parser.add_argument("--all", action="store_true", help="run all 13 configurations")
    parser.add_argument("--no-sim", action="store_true", help="compare existing files only")
    args = parser.parse_args()

    generate_all(ROOT / "mem")           # make sure the .mem tables exist and are correct

    worst = 0
    summary = []
    for tag, cfg in cases(args):
        print(f"\n=== {tag}: AW={cfg.aw} ROM={cfg.rom_arch} "
              f"amp_car={cfg.amp_car} amp_msg={cfg.amp_msg} ===")
        status, result = one_case(tag, cfg, args)
        worst = max(worst, status)
        if result:
            mark = "PASS" if result["passed"] else "FAIL"
            print(f"{mark}: {result['n_compared']} samples compared, "
                  f"{result['mismatches']} mismatches")
            if not result["passed"] and result.get("first_mismatch") is not None:
                print(f"  first mismatch at sample {result['first_mismatch']}: "
                      f"golden={result.get('golden_value')} rtl={result.get('rtl_value')}")
            summary.append((tag, mark, result["n_compared"], result["mismatches"]))

    if summary:
        print("\n" + "=" * 58)
        print(f"{'case':<18}{'result':<10}{'samples':>10}{'diff':>10}")
        for tag, mark, n, bad in summary:
            print(f"{tag:<18}{mark:<10}{n:>10}{bad:>10}")
        print("=" * 58)
        print("ALL CONFIGURATIONS PASS" if worst == 0 else "SOME CONFIGURATIONS FAILED")
    return worst


if __name__ == "__main__":
    sys.exit(main())
