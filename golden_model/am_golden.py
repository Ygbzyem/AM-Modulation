"""Sample-based integer AM reference. No RTL pipeline is simulated."""
import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

try:
    from .gen_sine_rom import quarter_lookup, sine_tables
except ImportError:
    from gen_sine_rom import quarter_lookup, sine_tables


@dataclass(frozen=True)
class Config:
    clock_hz: int = 100_000_000
    pw: int = 32
    aw: int = 8
    dw: int = 12
    ftw_car: int = 42_949_673
    ftw_msg: int = 858_993
    amp_car: int = 2000
    amp_msg: int = 1000
    samples: int = 10_000
    rom_arch: str = "FULL"
    initial_phase_car: int = 0
    initial_phase_msg: int = 0
    start_sample: int = 0

    def __post_init__(self):
        if not 3 <= self.aw <= 16 or not self.aw <= self.pw <= 64:
            raise ValueError("Require 3 <= AW <= 16 and AW <= PW <= 64")
        if self.dw != 12:
            raise ValueError("This datapath specification fixes DW=12 and shift=11")
        if self.rom_arch not in ("FULL", "QUARTER"):
            raise ValueError("ROM_ARCH must be FULL or QUARTER")
        if self.clock_hz <= 0 or self.samples <= 0 or self.start_sample < 0:
            raise ValueError("Clock/samples must be positive; start_sample must be nonnegative")
        for name in ("ftw_car", "ftw_msg", "initial_phase_car", "initial_phase_msg"):
            if not 0 <= getattr(self, name) < (1 << self.pw):
                raise ValueError(f"{name} must fit unsigned PW bits")
        for name in ("amp_car", "amp_msg"):
            if not 0 <= getattr(self, name) <= 4095:
                raise ValueError(f"{name} must fit unsigned 12 bits")


def generate(config):
    full, quarter = sine_tables(config.aw, config.dw)
    mask = (1 << config.pw) - 1
    phase_car = (config.initial_phase_car + config.start_sample * config.ftw_car) & mask
    phase_msg = (config.initial_phase_msg + config.start_sample * config.ftw_msg) & mask
    rows = []
    for index in range(config.samples):
        car_addr = phase_car >> (config.pw - config.aw)
        msg_addr = phase_msg >> (config.pw - config.aw)
        if config.rom_arch == "FULL":
            car, msg = full[car_addr], full[msg_addr]
        else:
            car = quarter_lookup(quarter, car_addr, config.aw)
            msg = quarter_lookup(quarter, msg_addr, config.aw)
        # Python signed >> floors, matching Verilog signed >>>.
        msg_term = (config.amp_msg * msg) >> 11
        env = config.amp_car + msg_term
        out = (env * car) >> 11
        if not -(1 << 13) <= env < (1 << 13) or not -32768 <= out <= 32767:
            raise OverflowError("Reference exceeds specified env/output width")
        rows.append({"n": config.start_sample + index, "phase_car": phase_car,
                     "phase_msg": phase_msg, "car_addr": car_addr, "msg_addr": msg_addr,
                     "car": car, "msg": msg, "msg_term": msg_term, "env": env, "out": out})
        phase_car = (phase_car + config.ftw_car) & mask
        phase_msg = (phase_msg + config.ftw_msg) & mask
    return rows


def metadata(config, rows):
    return {"config": asdict(config),
            "sample_contract": "address uses phase[n] before increment; phase[n]=(initial+n*FTW) mod 2**PW; no reset/pipeline warm-up samples",
            "fc_hz": config.ftw_car * config.clock_hz / (1 << config.pw),
            "fm_hz": config.ftw_msg * config.clock_hz / (1 << config.pw),
            "mu": config.amp_msg / config.amp_car if config.amp_car else None,
            "mode": "AM" if config.amp_car else "DSB-SC",
            "env_min": min(row["env"] for row in rows),
            "env_max": max(row["env"] for row in rows),
            "out_min": min(row["out"] for row in rows),
            "out_max": max(row["out"] for row in rows)}


def save(config, output, trace=None, meta=None):
    rows = generate(config)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(f"{row['out']}\n" for row in rows), encoding="ascii")
    if trace:
        trace = Path(trace)
        trace.parent.mkdir(parents=True, exist_ok=True)
        with trace.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    if meta:
        meta = Path(meta)
        meta.parent.mkdir(parents=True, exist_ok=True)
        meta.write_text(json.dumps(metadata(config, rows), indent=2) + "\n", encoding="utf-8")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("clock_hz", "pw", "aw", "ftw_car", "ftw_msg", "amp_car", "amp_msg",
                 "samples", "initial_phase_car", "initial_phase_msg", "start_sample"):
        parser.add_argument("--" + name.replace("_", "-"), type=int, default=getattr(Config(), name))
    parser.add_argument("--rom-arch", choices=["FULL", "QUARTER"], default="FULL")
    parser.add_argument("--output", type=Path, default=Path("golden.txt"))
    parser.add_argument("--trace", type=Path)
    parser.add_argument("--metadata", type=Path)
    args = vars(parser.parse_args())
    output, trace, meta = (args.pop(key) for key in ("output", "trace", "metadata"))
    config = Config(**args)
    rows = save(config, output, trace, meta)
    print(f"Wrote {len(rows)} samples to {output}; env={min(r['env'] for r in rows)}..{max(r['env'] for r in rows)}")


if __name__ == "__main__":
    main()
