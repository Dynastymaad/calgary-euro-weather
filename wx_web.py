"""
wx_web.py -- rebuild the six Append-page charts as a self-contained web page.

Every number is computed the way the workbook computes it:

  per run_date x target_date, over members 1..100
      Average = AVERAGE(members)
      25P     = PERCENTILE.INC(members, 0.25)      <- AGGREGATE(16,0,...,0.25)
      75P     = PERCENTILE.INC(members, 0.75)      <- AGGREGATE(16,0,...,0.75)
      Normal  = the daily climatology in wx_normals.json ('Weather Averages'!D)
      Lean    = 75P - Normal + 25P - Normal

  run vintages
      Todays Run / Yday / 2 Days Ago / 3 Days Ago = those single runs
      3 Day Average  = mean of Todays, Yday, 2 Days Ago      (three runs, as in the sheet)
      7/14/30 Day Average = mean of every run with run_date > Euro_date - N

Run from the repo folder:   python wx_web.py
Writes: wx_dashboard.html   (open it, or send it to be published)
"""
import json, sys
from pathlib import Path
from datetime import date, timedelta
import numpy as np, pandas as pd, pyodbc

HERE = Path(__file__).resolve().parent
OUT = HERE / 'wx_dashboard.html'
OUT_A = HERE / 'wx_dashboard_artifact.html'   # body-only, for publishing to a URL
OUT_D = HERE / 'docs' / 'index.html'          # what GitHub Pages serves
STATION, VARIABLE, NMEM = 'CYYC', 'tmax2m', 100
MEM = [str(i) for i in range(1, NMEM + 1)]

# lead -> weight, exactly the FW column
def weight(lead):
    if lead <= 4:  return 0.00
    if lead <= 11: return 0.75
    if lead <= 19: return 0.65
    if lead <= 28: return 0.50
    if lead <= 37: return 0.40
    return 0.15

VINT = ['Todays Run', 'Yday', '2 Days Ago', '3 Days Ago',
        '3 Day Average', '7 Day Average', '14 Day Average', '30 Day Average']
BUCKETS = [(1, 5), (6, 10), (11, 15), (16, 20), (21, 25), (26, 30), (31, 35), (36, 40)]
# (label, first lead, last lead) - the sheet's own row ranges, row 34 overlap included
RELNORM = [('Day 1-5', 0, 4), ('Day 6-10', 5, 9), ('Day 11-15', 10, 14),
           ('Day 16-30', 15, 29), ('Day 31-45', 29, 43), ('Day 1-45', 0, 43)]


def load_normals():
    p = HERE / 'wx_normals.json'
    if not p.exists():
        sys.exit("wx_normals.json is missing - it must sit next to this script.")
    return {k: float(v) for k, v in json.loads(p.read_text()).items()}


def pull():
    cfg = json.loads((HERE / 'db.json').read_text())['composition_db']
    cs = (f"Driver={{{cfg['driver']}}};Server={cfg['server']};Port={cfg['port']};"
          f"Database={cfg['database']};Uid={cfg['username']};Pwd={cfg['password']};"
          f"sslmode={cfg.get('sslmode','require')}")
    cols = ', '.join(f'"{c}"' for c in ['date', 'run_date'] + MEM)
    sql = (f'SELECT {cols} FROM canpower.aeso_euro_weekly_members_daily_minmax '
           f"WHERE variable = ? AND station = ? "
           f"AND run_date >= (SELECT MAX(run_date) - INTERVAL '40 days' "
           f'      FROM canpower.aeso_euro_weekly_members_daily_minmax)')
    with pyodbc.connect(cs, timeout=120) as cn:
        df = pd.read_sql(sql, cn, params=[VARIABLE, STATION])
    print(f'  pulled {len(df):,} rows, {df.run_date.nunique()} run dates')
    return df


def metrics(df, norm):
    M = df[MEM].to_numpy(dtype=float)
    q = np.nanpercentile(M, [25, 75], axis=1)          # PERCENTILE.INC
    out = pd.DataFrame({
        'run': pd.to_datetime(df.run_date).dt.date,
        'date': pd.to_datetime(df['date']).dt.date,
        'avg': np.nanmean(M, axis=1), 'p25': q[0], 'p75': q[1]})
    out['norm'] = out.date.map(lambda d: norm.get(d.isoformat()))
    out = out.dropna(subset=['norm'])
    out['lean'] = out.p75 - out.norm + out.p25 - out.norm
    out['lead'] = [(d - r).days for d, r in zip(out.date, out.run)]
    return out


def series(M, E, metric):
    """value of `metric` for the fixed target dates Euro_date+0..+43, per run vintage.

    The sheet keys on the TARGET DATE (column DN), not on each run's own lead -
    yesterday's run contributes its day-(L+1) forecast to target L."""
    targets = [E + timedelta(days=L) for L in range(44)]
    piv = M.pivot_table(index='date', columns='run', values=metric, aggfunc='mean')
    get = lambda t, r: (float(piv.at[t, r])
                        if (r in piv.columns and t in piv.index and pd.notna(piv.at[t, r]))
                        else None)
    idx = {v: {} for v in VINT}
    for name, back in [('Todays Run', 0), ('Yday', 1), ('2 Days Ago', 2), ('3 Days Ago', 3)]:
        r = E - timedelta(days=back)
        idx[name] = {L: get(t, r) for L, t in enumerate(targets)}
    for L in range(44):                                # 3 Day Average = mean of 3 runs
        v = [idx[n][L] for n in ('Todays Run', 'Yday', '2 Days Ago') if idx[n][L] is not None]
        idx['3 Day Average'][L] = float(np.mean(v)) if v else None
    for name, n in [('7 Day Average', 7), ('14 Day Average', 14), ('30 Day Average', 30)]:
        cols = [c for c in piv.columns if c > E - timedelta(days=n)]
        for L, t in enumerate(targets):
            v = [get(t, r) for r in cols]
            v = [x for x in v if x is not None]
            idx[name][L] = float(np.mean(v)) if v else None
    return idx


def bucketed(idx, lo, hi):
    out = {}
    for v in VINT:
        vals = [idx[v][L] for L in range(lo, hi + 1) if idx[v].get(L) is not None]
        out[v] = round(float(np.mean(vals)), 2) if vals else None
    return out


def build():
    norm = load_normals()
    print('pulling the ensemble...')
    M = metrics(pull(), norm)
    E = max(M.run)
    print(f'  Euro_date (latest run) = {E}')
    nrm = lambda L: norm.get((E + timedelta(days=L)).isoformat())

    S = {m: series(M, E, m) for m in ('avg', 'p25', 'p75', 'lean')}
    D = {'euro_date': E.isoformat(), 'station': STATION, 'charts': {}}

    def bucketchart(metric, title, extras):
        rows = []
        for lo, hi in BUCKETS:
            r = {'label': f'{lo}-{hi} Day'}
            r.update(bucketed(S[metric], lo, hi))
            n = [nrm(L) for L in range(lo, hi + 1) if nrm(L) is not None]
            base = round(float(np.mean(n)), 2) if n else None
            r['Average'] = base
            if 'low' in extras and base is not None:  r['Low Wind'] = round(base + 11, 2)
            if 'danger' in extras and base is not None: r['Danger'] = round(base - 15, 2)
            rows.append(r)
        lines = ['Average'] + (['Low Wind'] if 'low' in extras else []) \
                            + (['Danger'] if 'danger' in extras else [])
        return {'title': title, 'kind': 'bucket', 'rows': rows, 'bars': VINT, 'lines': lines}

    D['charts']['avg'] = bucketchart('avg',
        'Calgary: Average Euro Weekly High Temperatures (F)', ['low'])
    D['charts']['p10'] = bucketchart('p25',
        'Calgary: P10 Euro Weekly Temperatures (F)', ['low', 'danger'])
    D['charts']['p75'] = bucketchart('p75',
        'Calgary: P75 Euro Weekly Temperatures (F)', ['low', 'danger'])

    # Temperature Lean - 3-day rolling mean of the lean, by target date
    rows = []
    for L in range(44):
        r = {'label': (E + timedelta(days=L)).isoformat(), 'lead': L}
        for v in VINT:
            w = [S['lean'][v][k] for k in (L, L + 1, L + 2) if S['lean'][v].get(k) is not None]
            r[v] = round(float(np.mean(w)), 2) if w else None
        r['Danger'] = -20
        rows.append(r)
    D['charts']['lean'] = {'title': 'Calgary: Temperature Lean (P90 - Average + P10 - Average)',
                           'kind': 'line', 'rows': rows, 'bars': VINT, 'lines': ['Danger']}

    # Runs relative to normals - mean lean over the sheet's own day ranges
    rows = []
    for lab, lo, hi in RELNORM:
        r = {'label': lab}
        for v in VINT:
            w = [S['lean'][v][L] for L in range(lo, hi + 1) if S['lean'][v].get(L) is not None]
            r[v] = round(float(np.mean(w)), 2) if w else None
        rows.append(r)
    D['charts']['relnorm'] = {'title': 'Calgary: Euro Weekly Runs Relative to Normals (F)',
                              'kind': 'bucket', 'rows': rows, 'bars': VINT, 'lines': []}

    # Weighted average weather by run
    den = sum(weight(L) for L in range(44))            # FW50, leads 0..43
    CATS = [('Today', 'Todays Run'), ('Yesterday', 'Yday'), ('Two Days Ago', '2 Days Ago'),
            ('Three Days Ago', '3 Days Ago'), ('Three Day Average', '3 Day Average')]
    rows = []
    for lab, v in CATS:
        num = sum(weight(L) * S['avg'][v][L] for L in range(42)     # SUMPRODUCT rows 5..46
                  if S['avg'][v].get(L) is not None)
        rows.append({'label': lab, 'Weighted': round(num / den, 2)})
    sn = sum(weight(L) * nrm(L) for L in range(42) if nrm(L) is not None)
    rows.append({'label': 'Season Average', 'Weighted': round(sn / den, 2)})
    base = rows[-1]['Weighted']
    for r in rows: r['vs Normal'] = round(r['Weighted'] - base, 2)
    D['charts']['weighted'] = {'title': 'Weighted Average Weather by Run',
                               'kind': 'single', 'rows': rows,
                               'bars': ['Weighted'], 'lines': []}
    return D


if __name__ == '__main__':
    D = build()
    tpl = (HERE / 'wx_template.html').read_text(encoding='utf-8')
    page = tpl.replace('__PAYLOAD__', json.dumps(D, separators=(',', ':')))
    OUT.write_text(page, encoding='utf-8')
    # the hosted version: <title> + <style> + the body content, no document skeleton
    css = page[page.index('<style>'):page.index('</style>') + len('</style>')]
    body = page[page.index('<body>') + len('<body>'):page.rindex('</body>')]
    OUT_A.write_text('<title>Calgary Euro Weather</title>\n' + css + '\n' + body,
                     encoding='utf-8')
    OUT_D.parent.mkdir(exist_ok=True)
    OUT_D.write_text(page, encoding='utf-8')   # same standalone page, for Pages
    print(f'\nwrote {OUT}\n      {OUT_D}  (commit + push this one for GitHub Pages)'
          f'\n      {OUT_A}  (body-only, for a hosted artifact)')
    print(f'  Euro_date {D["euro_date"]}   charts: {", ".join(D["charts"])}')
    for k, c in D['charts'].items():
        r0 = c['rows'][0]
        print(f'   {k:>8}: {len(c["rows"])} rows, first = '
              + ', '.join(f'{b}={r0.get(b)}' for b in c['bars'][:3]))
