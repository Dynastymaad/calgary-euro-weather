# Calgary Euro Weather

A web replacement for the six Append-page charts in the *Weather Data* workbook.
It reads the ECMWF ensemble straight from the `canpower` schema, computes the same
numbers the spreadsheet computed, and writes a single self-contained HTML page.

No Excel, no external workbook links, no macros.

## The charts

| Chart | Metric | Shape |
|---|---|---|
| Calgary: Average Euro Weekly High Temperatures (F) | mean of members | 8 lead buckets x 8 run vintages |
| Calgary: P10 Euro Weekly Temperatures (F) | 25th percentile *(see note)* | 8 lead buckets x 8 run vintages |
| Calgary: P75 Euro Weekly Temperatures (F) | 75th percentile | 8 lead buckets x 8 run vintages |
| Calgary: Temperature Lean | (75P - normal) + (25P - normal) | 44 target dates, 3-day rolling |
| Calgary: Euro Weekly Runs Relative to Normals (F) | mean lean | 6 day ranges x 8 run vintages |
| Weighted Average Weather by Run | lead-weighted mean high | 6 run vintages |

Every legend entry from the workbook is present: the eight run vintages plus
**Average** (normal), **Low Wind** (normal + 11) and **Danger** (normal - 15).
Clicking a legend entry hides that series across all six charts. Each chart has a
"Numbers" drawer with the underlying table.

`docs/CHART_SPEC.md` has the cell-by-cell mapping back to the workbook, and the
verification against its cached values.

## Setup

```bash
git clone https://github.com/<you>/calgary-euro-weather.git
cd calgary-euro-weather
pip install -r requirements.txt
cp db.example.json db.json        # then fill in the sandbox Postgres credentials
```

`db.json` is gitignored and must never be committed.

You also need an ODBC driver for PostgreSQL. On Windows that is the
"PostgreSQL Unicode" driver from the psqlODBC installer; set `driver` in
`db.json` to whatever name appears in the ODBC Data Source Administrator.

## Refreshing

```bash
python wx_web.py          # or: refresh.bat
```

Roughly ten seconds. It writes three files:

- **`docs/index.html`** - what GitHub Pages serves. Committed deliberately.
- **`wx_dashboard.html`** - the same page at the repo root, for opening locally.
- **`wx_dashboard_artifact.html`** - the same page with the document skeleton
  stripped, for publishing to a hosted artifact URL.

The last two are gitignored; `docs/index.html` is not, because it is the site.

## Publishing to a URL

Settings -> Pages -> Source: **Deploy from a branch**, Branch: **main**, Folder:
**/docs**. The refresh then becomes:

```bash
python wx_web.py
git add -A && git commit -m "refresh" && git push
```

The page is live a minute or so later at
`https://<you>.github.io/calgary-euro-weather/`.

**Before making this public**, see *Licensing* below.

## Licensing

The ensemble values are ECMWF data delivered through a commercial feed. Publishing
them on a public site is a redistribution question, not a technical one - check the
vendor terms before turning Pages on for a public repo. A private repo with Pages
(GitHub Pro or Team) keeps the page behind sign-in; so does any internal host.

## Data source

`canpower.aeso_euro_weekly_members_daily_minmax` on the sandbox Postgres.
One row per `(variable, station, run_date, date)` with `ctl` plus 100 perturbed
members. This project reads `variable = 'tmax2m'`, `station = 'CYYC'`, and the
most recent 40 run dates.

`wx_normals.json` is the daily Calgary climatology lifted from the workbook's
*Weather Averages* sheet - 2,403 days, 2024-01-01 to 2030-07-31, degrees F. It is
static reference data and is committed deliberately.

## Notes carried over from the workbook

Three quirks were reproduced rather than corrected, so the numbers tie out. Say
the word and any of them can be fixed.

1. **"P10" is really P25.** The workbook's P10 chart points at the same cell range
   as its P75 chart, so its series were never repointed. The only lower percentile
   the sheet computes is `AGGREGATE(16,0,...,0.25)` - `PERCENTILE.INC` at 25%.
2. **The Lean title says P90/P10**, but the formula in column DG is
   `75P - normal + 25P - normal`. The formula is what runs.
3. **P75 used to include the control run.** Column `DE` read `E5:DA5` while `DC`
   and `DD` read `F5:DA5`. Almost certainly a drag error, worth about 0.05 F.
   This project uses members 1-100 for all three.
