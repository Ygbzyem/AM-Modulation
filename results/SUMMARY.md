# Part A Python results

These are reference-model results, not RTL verification or implementation measurements.

All 6 ROMs reconstruct bit-exactly. All 13 Python FULL/QUARTER output pairs agree.

SFDR uses a periodic Hann window, +/-3 FFT-bin exclusion per intended tone, and includes DC as a spur.
AM excludes intended sidebands; NCO excludes only the fundamental. Both are finite-record estimates.

| Case | Env min | Env max | AM SFDR dB | NCO SFDR dB | RTL |
|---|---:|---:|---:|---:|---|
| functional_mu_0 | 2000 | 2000 | 48.17 | 48.07 | NOT_RUN |
| functional_mu_0.25 | 1500 | 2499 | 48.06 | 48.07 | NOT_RUN |
| functional_mu_0.5 | 1000 | 2999 | 48.07 | 48.07 | NOT_RUN |
| functional_mu_1 | 0 | 3999 | 48.07 | 48.07 | NOT_RUN |
| functional_mu_1.5 | -999 | 4998 | 48.07 | 48.07 | NOT_RUN |
| functional_dsb_sc | -1000 | 999 | 47.95 | 48.07 | NOT_RUN |
| functional_fm_100k | 1000 | 2999 | 48.07 | 48.07 | NOT_RUN |
| rom_aw8_full | 1000 | 2999 | 48.07 | 48.07 | NOT_RUN |
| rom_aw8_quarter | 1000 | 2999 | 48.07 | 48.07 | NOT_RUN |
| rom_aw10_full | 1000 | 2999 | 60.72 | 60.67 | NOT_RUN |
| rom_aw10_quarter | 1000 | 2999 | 60.72 | 60.67 | NOT_RUN |
| rom_aw12_full | 1000 | 2999 | 71.88 | 72.03 | NOT_RUN |
| rom_aw12_quarter | 1000 | 2999 | 71.88 | 72.03 | NOT_RUN |
