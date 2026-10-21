# Chart spec — how each number is built

> **Updated Oct 2026:** P75 → P90, P10 is a true 10th percentile, Lean = P90 − normal + P10 − normal, buckets now start at lead 0 (1-5 Day = today..today+4), normals are looked up by MM-DD, and the bucket charts carry Average, Summer Low Wind (+10), Summer Danger (+17), Winter Low Wind (−10) and Winter Danger (−17). The workbook mapping below is kept for reference; the verification table predates these changes.

Reverse-engineered from the `Append` sheet of *Weather Data.xlsx*, then verified
against that workbook's own cached values. Cell references below are the
workbook's, kept so the two can be reconciled later.

## Source rows

One row per `(run_date, target_date)`, members `1`..`100`:

| Workbook | Header | Formula | Here |
|---|---|---|---|
| `DC` | Average | `=AVERAGE(F:DA)` | `avg` |
| `DD` | 25P | `=AGGREGATE(16,0,F:DA,0.25)` | `p25` |
| `DE` | 75P | `=AGGREGATE(16,0,E:DA,0.75)` | `p75` |
| `DF` | Average | `=VLOOKUP(date,'Weather Averages'!A:D,4,TRUE)` | `norm` |
| `DG` | Lean | `=DE-DF+DD-DF` | `lean` |

`AGGREGATE` function 16 is `PERCENTILE.INC`, which is numpy's default linear
interpolation — so `np.nanpercentile` matches Excel exactly.

## Run vintages

`Euro_date` is the most recent `run_date` in the table. The workbook keys every
vintage on the **target date** (column `DN`), not on each run's own lead — so
yesterday's run contributes its day-(L+1) forecast to target slot L. Getting this
wrong warms the 30-day average by up to 7.5 F.

| Series | Definition |
|---|---|
| Todays Run | `run_date = Euro_date` |
| Yday / 2 Days Ago / 3 Days Ago | `Euro_date - 1 / 2 / 3` |
| 3 Day Average | mean of Todays, Yday, 2 Days Ago — **three** runs (`=AVERAGE(DO:DQ)`) |
| 7 / 14 / 30 Day Average | mean of every run with `run_date > Euro_date - N` |

## Chart 1 — Average Euro Weekly High Temperatures

Buckets `1-5, 6-10, 11-15, 16-20, 21-25, 26-30, 31-35, 36-40` days ahead of
`Euro_date`; each cell is the mean of `avg` over that bucket's target dates.
Reference lines: **Average** = mean daily normal over the bucket,
**Low Wind** = Average + 11.

## Chart 2 — "P10" — and Chart 3 — P75

Identical to chart 1 with `p25` and `p75` in place of `avg`. Both add
**Danger** = Average − 15. See the README note on the P10 label.

## Chart 4 — Temperature Lean

x-axis is the 44 target dates. Each vintage's value at target L is the mean of
`lean` at L, L+1, L+2 (`=AVERAGE(EO5:EO7)`). A flat **Danger** line sits at −20.

## Chart 5 — Euro Weekly Runs Relative to Normals

Mean `lean` over the sheet's own day ranges, which are not contiguous — the
Day 31-45 range starts on the row Day 16-30 ends on, and that overlap is
reproduced:

| Label | Rows | Leads |
|---|---|---|
| Day 1-5 | `EO5:EO9` | 0–4 |
| Day 6-10 | `EO10:EO14` | 5–9 |
| Day 11-15 | `EO15:EO19` | 10–14 |
| Day 16-30 | `EO20:EO34` | 15–29 |
| Day 31-45 | `EO34:EO48` | **29**–43 |
| Day 1-45 | `EO5:EO48` | 0–43 |

## Chart 6 — Weighted Average Weather by Run

Lead weights, from column `FW`:

| Lead | 0–4 | 5–11 | 12–19 | 20–28 | 29–37 | 38–43 |
|---|---|---|---|---|---|---|
| Weight | 0.00 | 0.75 | 0.65 | 0.50 | 0.40 | 0.15 |

`value = SUMPRODUCT(weights[0..41], avg[0..41]) / SUM(weights[0..43])`

The numerator stops at lead 41 (`FY51` uses rows 5:46) while the denominator runs
to lead 43 (`FW50` sums rows 5:48). That asymmetry is in the workbook and is
reproduced — the denominator is 19.45. Categories are Today, Yesterday, Two Days
Ago, Three Days Ago, Three Day Average, and Season Average (the weighted normal).

## Verification

Against the workbook's cached values at `Euro_date = 2026-09-22`:

| Check | This code | Workbook |
|---|---|---|
| Avg high, 1-5 Day, Todays Run | 61.11 | 61.11 |
| Avg high, 36-40 Day, 30 Day Average | 46.12 | 46.12 |
| Lean, Day 6-10, Todays Run | −7.48 | −7.53 |
| Lean, Day 1-45, 30 Day Average | 1.87 | 1.86 |
| Weighted, Today | 55.06 | 55.06 |
| Weighted, Season Average | 53.89 | 53.89 |
| Weight denominator | 19.45 | 19.45 |

All 64 cells of chart 1 agree to two decimals. The 8 bucket normals reproduce to
the cent from the daily climatology in `wx_normals.json`.
