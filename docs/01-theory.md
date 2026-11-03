# 01 — Lý thuyết điều chế AM và bộ tạo sóng NCO

## 1. Điều chế AM (DSB-FC)

Sóng AM có sóng mang đầy đủ:

```
s(t) = A_c · [1 + μ · m(t)] · cos(2π f_c t),        |m(t)| ≤ 1
μ    = A_m / A_c        (chỉ số điều chế)
```

Với bản tin hình sin `m(t) = cos(2π f_m t)`:

```
s(t) = A_c cos(2π f_c t)
     + (μ A_c / 2) cos(2π (f_c + f_m) t)
     + (μ A_c / 2) cos(2π (f_c − f_m) t)
```

| Đại lượng | Công thức | Giá trị của nhóm |
| --- | --- | --- |
| Các vạch phổ | f_c − f_m, f_c, f_c + f_m | 980 / 1000 / 1020 kHz |
| Tỉ lệ vạch bên / vạch giữa | μ / 2 | 0,25 (−12,04 dB) |
| Băng thông | B = 2 f_m | 40 kHz |
| Hiệu suất công suất (bản tin sin) | η = μ² / (2 + μ²) | 0,25 / 2,25 ≈ 11,1 % |

**Ba chế độ theo μ**

| μ | Đường bao `A_c(1 + μ m)` | Hệ quả |
| --- | --- | --- |
| < 1 | luôn dương | điều chế đúng; tách sóng đường bao lấy lại được bản tin |
| = 1 | chạm 0 | tới hạn (100 % điều chế) |
| > 1 | đổi dấu | **quá điều chế**: đường bao bị gập, máy thu tách sóng đường bao cho ra tín hiệu méo |

Quá điều chế là hiện tượng ở phía thu: tín hiệu phát vẫn là tích tuyến tính
`env × car`, nên phổ vẫn đúng ba vạch. Quá điều chế thể hiện qua `env_min < 0`
(case μ = 1,5: `env` chạy từ −999 đến 4998).

**DSB-SC** (`amp_car = 0`): số hạng `1` biến mất, vạch giữa mất, chỉ còn hai vạch bên
với biên độ `A_m/2`. Tỉ lệ "vạch bên / vạch giữa" không còn xác định, nên cột
`ratio` trong sheet Spectrum để trống ở case 6.

## 2. Tính bằng số nguyên (fixed-point)

Quy ước: số nguyên `2047` đại diện cho 1,0. Mỗi phép nhân hai số kiểu này
mang hệ số `2048` thêm một lần, nên sau nhân dịch phải 11 bit (`>>> 11`).

```
msg_term = (amp_msg × msg) >>> 11        // 12b × 12b = 25b → 14b
env      = amp_car + msg_term            // 14b có dấu
am_out   = (env × car) >>> 11            // 14b × 12b = 26b → 16b
```

Dịch phải số có dấu làm tròn về phía **−∞** (999,5 → 999 nhưng −999,5 → −1000).
Đó là lý do Python dùng `>>` chứ không dùng `//` hay `int()` trong mô hình chuẩn.

Vì `2047/2048 ≈ 0,9995`, biên độ vạch sóng mang đo được hơi nhỏ hơn `amp_car`
(≈ 1998 thay vì 2000).

## 3. NCO / DDS

Bộ cộng pha 32 bit cộng `FTW` mỗi nhịp clock; `AW` bit cao của thanh ghi pha làm địa chỉ bảng sin.

```
f_out = FTW × f_clk / 2^32           độ phân giải = f_clk / 2^32 ≈ 0,0233 Hz
FTW   = f_out × 2^32 / f_clk
```

| f mong muốn | FTW (làm tròn) | f thực tế |
| --- | --- | --- |
| 1 MHz | 42 949 673 | 1 000 000,0 Hz (sai số < 0,01 Hz) |
| 20 kHz | 858 993 | 19 999,99 Hz |
| 100 kHz | 4 294 967 | 99 999,99 Hz |

**Phase truncation.** Chỉ dùng `AW` trong 32 bit pha làm địa chỉ nên sinh ra các vạch nhiễu.
Quy tắc gần đúng: mỗi bit địa chỉ thêm vào cải thiện SFDR cỡ 6 dB, tức xấp xỉ
`6,02 × AW` dB: khoảng 48 / 60 / 72 dB cho AW = 8 / 10 / 12. Đây là lý do nhóm quét ba giá trị AW,
và là giá trị để đối chiếu cột SFDR trong `results.xlsx`.

## 4. Hai kiến trúc ROM

Bảng đầy đủ lưu `2^AW` ô × 12 bit. Bảng quarter-wave chỉ lưu `2^(AW−2)` ô,
dựng lại cả vòng bằng hai bit cao của pha: bit `AW−2` để **lật địa chỉ** (`~addr`),
bit `AW−1` để **đảo dấu**.

| AW | Full (ô) | Quarter (ô) | Full (bit) | Quarter (bit) | Tiết kiệm |
| --- | --- | --- | --- | --- | --- |
| 8 | 256 | 64 | 3 072 | 768 | 75 % |
| 10 | 1 024 | 256 | 12 288 | 3 072 | 75 % |
| 12 | 4 096 | 1 024 | 49 152 | 12 288 | 75 % |

Điều kiện để so sánh công bằng: bảng sinh với `(n + 0,5)` để đối xứng hoàn hảo,
và cả hai ROM có đúng 2 tầng thanh ghi (cùng độ trễ).

Giả thuyết của nhóm: quarter-wave dùng ít bộ nhớ hơn (BRAM hoặc LUTRAM) nhưng nhiều LUT hơn
(mạch lật địa chỉ và đảo dấu), và lợi rõ hơn khi AW lớn.

## 5. Chỉ số đánh giá

| Chỉ số | Định nghĩa | Nguồn |
| --- | --- | --- |
| Bit-exact | 10 000 mẫu RTL khớp từng mẫu với mô hình chuẩn sau khi bỏ 3 mẫu khởi động của pipeline | `model/compare.py` |
| SFDR | vạch mong muốn lớn nhất ÷ bin lớn nhất ngoài các vạch mong muốn (cửa sổ Hann, loại ±3 bin quanh mỗi vạch, DC tính là nhiễu), đơn vị dB | `model/spectrum.py` |
| LUT, FF, LUTRAM, BRAM, DSP | bảng `report_utilization` | `results/rpt/*/utilization.rpt` |
| WNS | thời gian dư của đường chậm nhất, dương là đạt | `results/rpt/*/timing.rpt` |
| Fmax | `1 / (10 ns − WNS)` | tính từ WNS |
| Công suất động | mục `Dynamic (W)` | `results/rpt/*/power.rpt` |
