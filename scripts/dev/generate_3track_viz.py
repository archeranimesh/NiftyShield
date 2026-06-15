"""Generate self-contained HTML visualization for the 3-Track comparison strategy.

Run:
    python scripts/dev/generate_3track_viz.py
    python scripts/dev/generate_3track_viz.py --output docs/viz/3track_comparison.html

Output: docs/viz/3track_comparison.html (default)

Add to EOD cron after paper_3track_snapshot.py to keep the viz current.
"""

import argparse
import sqlite3
from pathlib import Path

_SCRIPT_NAME = "scripts.dev.generate_3track_viz"

DB_PATH = Path("data/portfolio/portfolio.sqlite")
DEFAULT_OUT = Path("docs/viz/3track_comparison.html")

TRACKS = {
    "NiftyBees": ("paper_nifty_spot", "base_etf"),
    "Futures": ("paper_nifty_futures", "base_futures"),
    "DITM": ("paper_nifty_proxy", "base_ditm_call"),
}

# Which overlays exist per track
OVERLAYS: dict[str, list[str]] = {
    "NiftyBees": ["cc", "pp", "collar"],
    "Futures": ["pp", "collar"],
    "DITM": ["cc", "pp", "collar"],
}

OVERLAY_LEGS: dict[str, list[str]] = {
    "cc": ["overlay_cc"],
    "pp": ["overlay_pp"],
    "collar": ["overlay_collar_call", "overlay_collar_put"],
}


def _fetch_data(conn: sqlite3.Connection) -> dict:
    cur = conn.cursor()

    # Leg snapshots: sum unrealized + realized per (date, strategy, leg_role)
    cur.execute(
        """
        SELECT strategy_name, leg_role, snapshot_date,
               CAST(unrealized_pnl AS REAL) + CAST(realized_pnl AS REAL) AS pnl
        FROM paper_leg_snapshots
        ORDER BY snapshot_date
        """
    )
    by_date: dict[str, dict[str, dict[str, float]]] = {}
    for row in cur.fetchall():
        sname, leg, date, pnl = row
        by_date.setdefault(date, {}).setdefault(sname, {})[leg] = round(float(pnl), 2)

    dates = sorted(by_date.keys())

    # Spot price series
    cur.execute(
        """
        SELECT snapshot_date, underlying_price FROM paper_nav_snapshots
        WHERE strategy_name = 'paper_nifty_spot' ORDER BY snapshot_date
        """
    )
    price_map = {r[0]: float(r[1]) for r in cur.fetchall() if r[1]}
    spot = [price_map.get(d, 0.0) for d in dates]

    def sum_legs(date: str, strategy: str, legs: list[str]) -> float:
        d = by_date.get(date, {}).get(strategy, {})
        return round(sum(d.get(leg, 0.0) for leg in legs), 2)

    series: dict[str, dict] = {}
    for track, (sname, base_leg) in TRACKS.items():
        entry: dict[str, list | None] = {"base": [sum_legs(d, sname, [base_leg]) for d in dates]}
        for ov in ["cc", "pp", "collar"]:
            if ov in OVERLAYS[track]:
                ov_legs = [base_leg] + OVERLAY_LEGS[ov]
                entry[ov] = [sum_legs(d, sname, ov_legs) for d in dates]
            else:
                entry[ov] = None
        series[track] = entry

    return {"dates": dates, "series": series, "spot": spot}


def _html(data: dict) -> str:
    import json

    dates = data["dates"]
    series = data["series"]
    spot = data["spot"]
    last_date = dates[-1] if dates else "—"

    # Short date labels: "May 11" etc.
    def fmt_date(d: str) -> str:
        from datetime import date as dt

        obj = dt.fromisoformat(d)
        return obj.strftime("%-d %b")

    labels_js = json.dumps([fmt_date(d) for d in dates])
    series_js = json.dumps(series)
    spot_js = json.dumps(spot)

    track_colors = {
        "NiftyBees": "#1976D2",
        "Futures": "#E65100",
        "DITM": "#2E7D32",
    }
    track_colors_js = json.dumps(track_colors)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>NiftyShield — 3-Track Comparison</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f1117;color:#e0e0e0;min-height:100vh}}
  header{{background:#1a1d2e;border-bottom:1px solid #2a2d3e;padding:14px 24px;display:flex;align-items:center;gap:16px}}
  header h1{{font-size:1.1rem;font-weight:600;letter-spacing:.5px;color:#fff}}
  header .badge{{font-size:.75rem;background:#263238;border:1px solid #37474f;padding:3px 10px;border-radius:20px;color:#90caf9}}
  .tabs{{display:flex;gap:0;background:#1a1d2e;border-bottom:1px solid #2a2d3e;padding:0 24px}}
  .tab{{padding:10px 18px;cursor:pointer;font-size:.85rem;color:#9e9e9e;border-bottom:2px solid transparent;transition:.15s}}
  .tab:hover{{color:#e0e0e0}}
  .tab.active{{color:#90caf9;border-bottom-color:#90caf9;font-weight:600}}
  .panel{{display:none;padding:20px 24px}}
  .panel.active{{display:block}}
  .chart-wrap{{background:#1a1d2e;border:1px solid #2a2d3e;border-radius:8px;padding:16px;margin-bottom:20px}}
  .chart-wrap h2{{font-size:.85rem;font-weight:600;color:#b0bec5;margin-bottom:12px;text-transform:uppercase;letter-spacing:.5px}}
  .chart-container{{position:relative;height:320px}}
  .summary-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:20px}}
  .card{{background:#1a1d2e;border:1px solid #2a2d3e;border-radius:8px;padding:14px 16px}}
  .card .label{{font-size:.72rem;color:#78909c;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}}
  .card .value{{font-size:1.15rem;font-weight:700}}
  .card .sub{{font-size:.78rem;color:#78909c;margin-top:2px}}
  .pos{{color:#66bb6a}}.neg{{color:#ef5350}}
  .legend-row{{display:flex;flex-wrap:wrap;gap:14px;margin-bottom:14px}}
  .legend-item{{display:flex;align-items:center;gap:6px;font-size:.78rem;color:#b0bec5}}
  .legend-line{{width:28px;height:3px;border-radius:2px}}
  canvas{{display:block}}
  .two-col{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
  @media(max-width:720px){{.two-col{{grid-template-columns:1fr}}}}
</style>
</head>
<body>

<header>
  <h1>NiftyShield · 3-Track Comparison</h1>
  <span class="badge">Inception → {last_date}</span>
  <span class="badge" style="margin-left:auto;color:#80cbc4">{len(dates)} trading days</span>
</header>

<div class="tabs">
  <div class="tab active" onclick="switchTab('overview',this)">Overview</div>
  <div class="tab" onclick="switchTab('niftybees',this)">NiftyBees</div>
  <div class="tab" onclick="switchTab('futures',this)">Futures</div>
  <div class="tab" onclick="switchTab('ditm',this)">DITM</div>
</div>

<!-- OVERVIEW -->
<div id="panel-overview" class="panel active">
  <div class="summary-grid" id="summary-cards"></div>
  <div class="chart-wrap">
    <h2>Base Track Comparison (₹ P&amp;L from inception)</h2>
    <div class="legend-row">
      <div class="legend-item"><div class="legend-line" style="background:#1976D2"></div>NiftyBees</div>
      <div class="legend-item"><div class="legend-line" style="background:#E65100"></div>Futures</div>
      <div class="legend-item"><div class="legend-line" style="background:#2E7D32"></div>DITM</div>
    </div>
    <div class="chart-container"><canvas id="chart-overview-base"></canvas></div>
  </div>
  <div class="two-col">
    <div class="chart-wrap">
      <h2>Overlay Impact — NiftyBees vs Futures (Collar)</h2>
      <div class="chart-container"><canvas id="chart-overview-collar"></canvas></div>
    </div>
    <div class="chart-wrap">
      <h2>Nifty Spot Price</h2>
      <div class="chart-container"><canvas id="chart-spot"></canvas></div>
    </div>
  </div>
</div>

<!-- NIFTYBEES -->
<div id="panel-niftybees" class="panel">
  <div class="chart-wrap">
    <h2>NiftyBees — Base vs Overlays (₹ P&amp;L)</h2>
    <div class="legend-row">
      <div class="legend-item"><div class="legend-line" style="background:#1976D2"></div>Base ETF</div>
      <div class="legend-item"><div class="legend-line" style="background:#1976D2;opacity:.7;border-top:2px dashed #1976D2;background:transparent;width:28px"></div>+ CC</div>
      <div class="legend-item"><div class="legend-line" style="background:#1976D2;opacity:.7;border-top:2px dotted #42a5f5;background:transparent;width:28px"></div>+ PP</div>
      <div class="legend-item"><div class="legend-line" style="background:#1976D2;opacity:.7;border-top:2px dashed #80d8ff;background:transparent;width:28px"></div>+ Collar</div>
    </div>
    <div class="chart-container" style="height:360px"><canvas id="chart-niftybees"></canvas></div>
  </div>
  <div class="two-col">
    <div class="chart-wrap">
      <h2>Overlay Benefit vs Base (Δ₹)</h2>
      <div class="chart-container"><canvas id="chart-niftybees-delta"></canvas></div>
    </div>
    <div class="chart-wrap">
      <h2>Cumulative Overlay Contribution</h2>
      <div class="chart-container"><canvas id="chart-niftybees-overlay"></canvas></div>
    </div>
  </div>
</div>

<!-- FUTURES -->
<div id="panel-futures" class="panel">
  <div class="chart-wrap">
    <h2>Futures — Base vs Overlays (₹ P&amp;L)</h2>
    <div class="chart-container" style="height:360px"><canvas id="chart-futures"></canvas></div>
  </div>
  <div class="two-col">
    <div class="chart-wrap">
      <h2>Overlay Benefit vs Base (Δ₹)</h2>
      <div class="chart-container"><canvas id="chart-futures-delta"></canvas></div>
    </div>
    <div class="chart-wrap">
      <h2>Cumulative Overlay Contribution</h2>
      <div class="chart-container"><canvas id="chart-futures-overlay"></canvas></div>
    </div>
  </div>
</div>

<!-- DITM -->
<div id="panel-ditm" class="panel">
  <div class="chart-wrap">
    <h2>DITM Call — Base vs Overlays (₹ P&amp;L)</h2>
    <div class="chart-container" style="height:360px"><canvas id="chart-ditm"></canvas></div>
  </div>
  <div class="two-col">
    <div class="chart-wrap">
      <h2>Overlay Benefit vs Base (Δ₹)</h2>
      <div class="chart-container"><canvas id="chart-ditm-delta"></canvas></div>
    </div>
    <div class="chart-wrap">
      <h2>Cumulative Overlay Contribution</h2>
      <div class="chart-container"><canvas id="chart-ditm-overlay"></canvas></div>
    </div>
  </div>
</div>

<script>
const LABELS = {labels_js};
const S = {series_js};
const SPOT = {spot_js};
const TC = {track_colors_js};

const CHART_DEFAULTS = {{
  responsive: true,
  maintainAspectRatio: false,
  interaction: {{ mode: 'index', intersect: false }},
  plugins: {{
    legend: {{ display: false }},
    tooltip: {{
      backgroundColor: '#1e2130',
      borderColor: '#37474f',
      borderWidth: 1,
      titleColor: '#b0bec5',
      bodyColor: '#e0e0e0',
      padding: 10,
      callbacks: {{
        label: ctx => {{
          const v = ctx.parsed.y;
          const sign = v >= 0 ? '+' : '';
          return ` ${{ctx.dataset.label}}: ${{sign}}₹${{Math.abs(v).toLocaleString('en-IN', {{maximumFractionDigits:0}})}}${{v<0?'':''}}`;
        }}
      }}
    }}
  }},
  scales: {{
    x: {{ grid: {{ color: '#1e2130' }}, ticks: {{ color: '#546e7a', maxTicksLimit: 8 }} }},
    y: {{
      grid: {{ color: '#1e2130' }},
      ticks: {{
        color: '#546e7a',
        callback: v => (v>=0?'+':'')+'₹'+Math.abs(v/1000).toFixed(0)+'K'
      }}
    }}
  }}
}};

function makeDataset(label, data, color, dash=[]) {{
  return {{
    label, data,
    borderColor: color,
    backgroundColor: color + '18',
    borderWidth: dash.length ? 2 : 2.5,
    borderDash: dash,
    pointRadius: 2,
    pointHoverRadius: 5,
    tension: 0.3,
    fill: false,
  }};
}}

function pnlColor(v) {{ return v >= 0 ? '#66bb6a' : '#ef5350'; }}

// ---- OVERVIEW: Summary Cards ----
function buildSummaryCards() {{
  const container = document.getElementById('summary-cards');
  const trackInfo = [
    ['NiftyBees', 'NiftyBees ETF (Spot)', 'NiftyBees'],
    ['Futures', 'Nifty Futures', 'Futures'],
    ['DITM', 'DITM Call (Proxy)', 'DITM'],
  ];
  const ovNames = {{ cc:'+ CC', pp:'+ PP', collar:'+ Collar' }};
  const n = LABELS.length - 1;

  let html = '';
  for (const [key, title] of trackInfo) {{
    const base = S[key].base[n];
    const best = Object.entries({{ 'Base':base, ...Object.fromEntries(
      ['cc','pp','collar'].filter(o => S[key][o]).map(o => [ovNames[o], S[key][o][n]])
    )}}).sort((a,b)=>b[1]-a[1])[0];

    html += `<div class="card">
      <div class="label">${{title}}</div>
      <div class="value ${{base>=0?'pos':'neg'}}">${{base>=0?'+':''}}₹${{Math.abs(base).toLocaleString('en-IN',{{maximumFractionDigits:0}})}}</div>
      <div class="sub">Base only · Best: <b>${{best[0]}}</b> ${{best[1]>=0?'+':''}}₹${{Math.abs(best[1]).toLocaleString('en-IN',{{maximumFractionDigits:0}})}}</div>
    </div>`;
  }}
  // Spot price card
  const spotNow = SPOT[n];
  const spotStart = SPOT[0];
  const spotChg = ((spotNow - spotStart) / spotStart * 100).toFixed(2);
  html += `<div class="card">
    <div class="label">Nifty Spot</div>
    <div class="value">${{spotNow.toLocaleString('en-IN')}}</div>
    <div class="sub">Inception ${{spotStart.toLocaleString('en-IN')}} · ${{spotChg>=0?'+':''}}${{spotChg}}%</div>
  </div>`;
  container.innerHTML = html;
}}

// ---- Chart builders ----
function lineChart(id, datasets, opts={{}}) {{
  const ctx = document.getElementById(id).getContext('2d');
  return new Chart(ctx, {{
    type: 'line',
    data: {{ labels: LABELS, datasets }},
    options: {{ ...CHART_DEFAULTS, ...opts,
      scales: {{ ...CHART_DEFAULTS.scales, ...(opts.scales||{{}}) }},
      plugins: {{ ...CHART_DEFAULTS.plugins, ...(opts.plugins||{{}}) }}
    }}
  }});
}}

function buildOverviewCharts() {{
  // Base comparison
  lineChart('chart-overview-base', [
    makeDataset('NiftyBees', S.NiftyBees.base, TC.NiftyBees),
    makeDataset('Futures',   S.Futures.base,   TC.Futures),
    makeDataset('DITM',      S.DITM.base,      TC.DITM),
  ]);

  // Collar comparison across tracks
  lineChart('chart-overview-collar', [
    makeDataset('NiftyBees+Collar', S.NiftyBees.collar, TC.NiftyBees, [6,3]),
    makeDataset('NiftyBees Base',   S.NiftyBees.base,   TC.NiftyBees),
    makeDataset('Futures+Collar',   S.Futures.collar,   TC.Futures,  [6,3]),
    makeDataset('Futures Base',     S.Futures.base,     TC.Futures),
    makeDataset('DITM+Collar',      S.DITM.collar,      TC.DITM,     [6,3]),
    makeDataset('DITM Base',        S.DITM.base,        TC.DITM),
  ]);

  // Spot price
  const ctx = document.getElementById('chart-spot').getContext('2d');
  new Chart(ctx, {{
    type: 'line',
    data: {{ labels: LABELS, datasets: [{{
      label: 'Nifty Spot',
      data: SPOT,
      borderColor: '#b0bec5',
      borderWidth: 2,
      pointRadius: 2,
      tension: 0.3,
      fill: false,
    }}] }},
    options: {{ ...CHART_DEFAULTS,
      scales: {{
        x: CHART_DEFAULTS.scales.x,
        y: {{ grid: {{ color:'#1e2130' }}, ticks: {{ color:'#546e7a', callback: v => v.toLocaleString('en-IN') }} }}
      }},
      plugins: {{ ...CHART_DEFAULTS.plugins, tooltip: {{ ...CHART_DEFAULTS.plugins.tooltip,
        callbacks: {{ label: ctx => ` Spot: ${{ctx.parsed.y.toLocaleString('en-IN')}}` }}
      }} }}
    }}
  }});
}}

function buildTrackCharts(track, chartId, deltaId, overlayId) {{
  const color = TC[track];
  const s = S[track];
  const overlays = {{ cc: '#FF8F00', pp: '#7B1FA2', collar: '#00838F' }};
  const dashes  = {{ cc: [6,3], pp: [2,3], collar: [8,4] }};
  const labels  = {{ cc:'+ CC', pp:'+ PP', collar:'+ Collar' }};

  // Main chart: base + overlays
  const datasets = [makeDataset('Base', s.base, color)];
  for (const [ov, ovColor] of Object.entries(overlays)) {{
    if (s[ov]) datasets.push(makeDataset(labels[ov], s[ov], ovColor, dashes[ov]));
  }}
  lineChart(chartId, datasets);

  // Delta chart: overlay PnL - base PnL
  const deltaDs = [];
  for (const [ov, ovColor] of Object.entries(overlays)) {{
    if (s[ov]) {{
      const delta = s[ov].map((v, i) => Math.round((v - s.base[i]) * 100) / 100);
      deltaDs.push(makeDataset(labels[ov], delta, ovColor, dashes[ov]));
    }}
  }}
  const deltaOpts = {{
    scales: {{
      x: CHART_DEFAULTS.scales.x,
      y: {{ grid: {{ color:'#1e2130' }}, ticks: {{ color:'#546e7a',
        callback: v => (v>=0?'+':'')+'₹'+Math.abs(v/1000).toFixed(1)+'K'
      }} }}
    }}
  }};
  lineChart(deltaId, deltaDs, deltaOpts);

  // Overlay-only contribution (absolute pnl of overlay legs = base+ov - base)
  // Also show as area
  const ovDs = [];
  for (const [ov, ovColor] of Object.entries(overlays)) {{
    if (s[ov]) {{
      const contrib = s[ov].map((v, i) => Math.round((v - s.base[i]) * 100) / 100);
      ovDs.push({{ ...makeDataset(labels[ov], contrib, ovColor, dashes[ov]),
        fill: 'origin', backgroundColor: ovColor + '28' }});
    }}
  }}
  lineChart(overlayId, ovDs, deltaOpts);
}}

// ---- Tab switch ----
let chartsBuilt = {{ overview: false, niftybees: false, futures: false, ditm: false }};
function switchTab(name, el) {{
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('panel-' + name).classList.add('active');
  el.classList.add('active');
  if (!chartsBuilt[name]) {{ buildTab(name); chartsBuilt[name] = true; }}
}}

function buildTab(name) {{
  if (name === 'overview') buildOverviewCharts();
  else if (name === 'niftybees') buildTrackCharts('NiftyBees','chart-niftybees','chart-niftybees-delta','chart-niftybees-overlay');
  else if (name === 'futures')   buildTrackCharts('Futures','chart-futures','chart-futures-delta','chart-futures-overlay');
  else if (name === 'ditm')      buildTrackCharts('DITM','chart-ditm','chart-ditm-delta','chart-ditm-overlay');
}}

// Init
buildSummaryCards();
buildOverviewCharts();
chartsBuilt.overview = true;
</script>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate 3-track comparison HTML")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    data = _fetch_data(conn)
    conn.close()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    html = _html(data)
    args.output.write_text(html, encoding="utf-8")
    print(f"Written: {args.output} ({len(data['dates'])} trading days)")


if __name__ == "__main__":
    main()
