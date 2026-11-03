# 04 — Mô phỏng, tổng hợp và tạo results.xlsx

## Lệnh

```powershell
pip install -r scripts/requirements.txt
python model/gen_sine_rom.py
python scripts/run_experiments.py
python scripts/run_experiments.py --impl
```

`xvlog`, `xelab`, `xsim`, `vivado` phải có trong `PATH` (hoặc dùng `--vivado-bin <thư mục bin>`).
Đường dẫn repo không được chứa dấu tiếng Việt, vì xsim không đọc được đường dẫn có dấu.

Mã thoát của `run_experiments.py` là 0 khi 13 case đều PASS.

## Dây chuyền

| Bước | Công cụ | Đầu ra |
| --- | --- | --- |
| Golden | `model/am_golden.py` | `results/work/<case>/golden.txt` |
| Mô phỏng | `xvlog` → `xelab` → `xsim` (`scripts/run_sim.tcl`) | `results/work/<case>/am_out.txt` |
| So sánh | `model/compare.py`, `skip_rtl = 3`, `expected_samples = 10000` | PASS/FAIL, số mẫu lệch, mẫu lệch đầu tiên |
| Phổ và hình | `model/spectrum.py`, `model/plot_txt.py` | `results/figures/<case>_{waveform,spectrum}.png` |
| Tổng hợp | `vivado` + `scripts/sweep_impl.tcl` | `results/rpt/AW<aw>_<arch>/{utilization,timing,power}.rpt` |
| Gom | `scripts/write_excel.py` | `results/results.xlsx`, `results/summary.json`, `results/verification_run.csv` |

## Tham số

| Tham số | Truyền bằng | Giá trị |
| --- | --- | --- |
| `FTW_CAR`, `FTW_MSG`, `AMP_CAR`, `AMP_MSG`, `OUTFILE` | `xsim -testplusarg` | `scripts/cases.yaml` |
| `AW`, `USE_QUARTER_ROM`, `FULL_MEM_FILE`, `QUARTER_MEM_FILE` | bản sao testbench `results/work/<case>/tb_case.v` (chèn `#(...)` vào `u_dut`) | `scripts/cases.yaml`, `mem/` |
| Số mẫu ghi | bản sao testbench | `samples + latency` = 10 003 (bỏ 3 mẫu đầu thì còn 10 000) |

Testbench trong `tb/` không bị sửa. Top là `am_modulator_top`, tên module trong bản sao được thay cho tên trong testbench gốc.

## Độ trễ

Sau reset, `am_out` ra theo dạng `0, y0, y0, y0, y1, …` (y là mẫu golden): ba mẫu đầu là khởi động. Với `skip_rtl = 3`
phần còn lại khớp golden từng mẫu. Độ trễ này đặt cố định ở `defaults.latency` trong `scripts/cases.yaml`.

## Synthesis và implementation

```powershell
vivado -mode batch -source scripts/sweep_impl.tcl
vivado -mode batch -source scripts/sweep_impl.tcl -tclargs 10 QUARTER
```

| Thiết lập | Giá trị |
| --- | --- |
| Part | `xc7a35tcpg236-1` |
| Top | `am_modulator_top` |
| Generic | `AW`, `USE_QUARTER_ROM`, `FULL_MEM_FILE`, `QUARTER_MEM_FILE` (đường dẫn tuyệt đối tới `mem/`) |
| Chế độ | `synth_design -mode out_of_context` (`set ooc 0` để tắt) |
| Ràng buộc | `constraint/constraints.xdc`: clock 10 ns; `set_false_path` cho `rst`, `ftw_*`, `amp_*`, `am_out` |
| Các bước | `synth_design`, `opt_design`, `place_design`, `route_design` |

```
Fmax = 1 / (10 ns − WNS)
```

## results.xlsx

| Sheet | Nội dung |
| --- | --- |
| Summary | mỗi case một dòng: cấu hình, μ, băng thông, `env_min/max`, `out_min/max`, kết quả, số mẫu lệch, độ trễ, SFDR, LUT, FF, LUTRAM, BRAM, DSP, WNS, Fmax, công suất động, thư mục `.rpt` |
| Figures | waveform + envelope và phổ của từng case |
| Spectrum | ba vạch: tần số, biên độ, tỉ lệ so với sóng mang đo được và lý thuyết (1 và μ/2), sai số |

Các case `functional_*` dùng netlist `AW8_FULL`, cột tài nguyên lấy từ `results/rpt/AW8_FULL/`.
