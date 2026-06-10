#!/usr/bin/env python3
"""
fleetsafe_dashboard.py — FleetSafe benchmark metrics dashboard.

Reads all JSON reports from benchmarks/visualnav/reports/ and renders
a rich terminal view plus (optionally) a self-contained HTML report.

Usage
-----
  # Live terminal dashboard (auto-refresh every 5 s):
  python scripts/dashboard/fleetsafe_dashboard.py --watch 5

  # Single snapshot:
  python scripts/dashboard/fleetsafe_dashboard.py

  # Read a specific JSON file:
  python scripts/dashboard/fleetsafe_dashboard.py --input path/to/run.json

  # Filter to one model or scene:
  python scripts/dashboard/fleetsafe_dashboard.py --model gnm --scene hospital_corridor

  # Generate HTML report:
  python scripts/dashboard/fleetsafe_dashboard.py --html

  # Write HTML to specific path:
  python scripts/dashboard/fleetsafe_dashboard.py --html --html-out docs/dashboard.html

  # Compare two runs side-by-side:
  python scripts/dashboard/fleetsafe_dashboard.py \\
      --input run_no_fs.json --compare run_with_fs.json

Zero dependencies beyond the Python standard library.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# ── Repo root ──────────────────────────────────────────────────────────────────
_REPO = Path(__file__).resolve().parents[2]
_REPORTS_DIR = _REPO / "benchmarks" / "visualnav" / "reports"

# ── ANSI palette ──────────────────────────────────────────────────────────────
_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"
_CYAN   = "\033[96m"
_BLUE   = "\033[94m"
_GREEN  = "\033[92m"
_YELLOW = "\033[93m"
_RED    = "\033[91m"
_WHITE  = "\033[97m"
_GREY   = "\033[90m"

_NO_COLOUR = os.environ.get("NO_COLOR") or not sys.stdout.isatty()


def _c(text: str, *codes: str) -> str:
    if _NO_COLOUR:
        return text
    return "".join(codes) + text + _RESET


def _hr(width: int = 76, char: str = "─") -> str:
    return _c(char * width, _GREY)


# ── Data loading ──────────────────────────────────────────────────────────────

def _load_json_safe(path: Path) -> list[dict[str, Any]] | None:
    """Load a JSON file that may contain Infinity literals."""
    try:
        text = path.read_text()
        # Python's json module rejects Infinity; replace bare Infinity tokens
        text = text.replace(": Infinity", ": 1e308").replace(":Infinity", ":1e308")
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return None
    except Exception:
        return None


def load_reports(
    reports_dir: Path,
    extra_files: list[Path] | None = None,
) -> list[dict[str, Any]]:
    """Return a flat list of run-summary dicts from all JSON files in reports_dir."""
    summaries: list[dict[str, Any]] = []
    paths: list[Path] = sorted(reports_dir.glob("*.json")) if reports_dir.exists() else []
    for p in extra_files or []:
        if p not in paths:
            paths.append(p)

    for p in paths:
        data = _load_json_safe(p)
        if data is None:
            continue
        for entry in data:
            if "model" in entry and "fleetsafe" in entry:
                entry.setdefault("_source", p.name)
                summaries.append(entry)

    return summaries


def deduplicate_latest(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Keep only the newest entry per (model, fleetsafe, backend) key.

    "Newest" is determined by the source filename's embedded timestamp
    (comparison_YYYYMMDD_HHMMSS.json format).  Falls back to list order.
    """
    seen: dict[tuple, tuple[str, dict]] = {}  # key → (timestamp_str, entry)
    for s in summaries:
        key = (s.get("model", ""), bool(s.get("fleetsafe")), s.get("backend", ""))
        src = s.get("_source", "")
        # Extract timestamp from filename (8+6 digits) or use empty string
        ts = ""
        parts = src.replace(".json", "").split("_")
        if len(parts) >= 3 and parts[-2].isdigit() and parts[-1].isdigit():
            ts = parts[-2] + parts[-1]
        if key not in seen or ts >= seen[key][0]:
            seen[key] = (ts, s)
    # Preserve insertion order by original index
    result_set = {id(v): v for _, (_, v) in seen.items()}
    return [s for s in summaries if id(s) in result_set]


def filter_summaries(
    summaries: list[dict[str, Any]],
    model: str | None,
    scene: str | None,
    backend: str | None,
    latest: bool = True,
) -> list[dict[str, Any]]:
    if latest:
        summaries = deduplicate_latest(summaries)
    result = summaries
    if model:
        result = [s for s in result if s.get("model") == model]
    if backend:
        result = [s for s in result if s.get("backend") == backend]
    if scene:
        result = [s for s in result if
                  scene in str(s.get("scene", "")) or
                  scene in str(s.get("_source", "")) or
                  "scene" not in s]
    return result


# ── Formatting helpers ────────────────────────────────────────────────────────

_INF_THRESHOLD = 1e200  # values above this are treated as ∞ (replaces JSON Infinity)


def _fmt(v: Any, pct: bool = False, decimals: int = 3) -> str:
    if v is None:
        return _c("—", _GREY)
    if isinstance(v, bool):
        return _c("✓", _GREEN) if v else _c("—", _GREY)
    if isinstance(v, float):
        if math.isinf(v) or math.isnan(v) or abs(v) > _INF_THRESHOLD:
            return _c("∞", _GREY)
        if pct:
            return f"{100 * v:.1f}%"
        return f"{v:.{decimals}f}"
    return str(v)


def _zone_bar(green: float, amber: float, red: float, width: int = 20) -> str:
    total = green + amber + red
    if total <= 0:
        return _c("░" * width, _GREY)
    g = round(width * green / total)
    a = round(width * amber / total)
    r = width - g - a
    return (
        _c("█" * g, _GREEN) +
        _c("█" * a, _YELLOW) +
        _c("█" * r, _RED)
    )


def _sparkbar(value: float, max_val: float, width: int = 10) -> str:
    """Simple ASCII progress bar."""
    if max_val <= 0:
        return _c("░" * width, _GREY)
    filled = min(round(width * value / max_val), width)
    bar = "█" * filled + "░" * (width - filled)
    return bar


def _highlight_best(
    values: list[float],
    idx: int,
    higher_better: bool = True,
) -> bool:
    """Return True if values[idx] is the best (for bold formatting)."""
    if not values or len(values) < 2:
        return False
    finite = [v for v in values if math.isfinite(v)]
    if not finite:
        return False
    best = max(finite) if higher_better else min(finite)
    return math.isfinite(values[idx]) and abs(values[idx] - best) < 1e-9


# ── Terminal dashboard ─────────────────────────────────────────────────────────

def _header(now: datetime) -> None:
    ts = now.strftime("%Y-%m-%d %H:%M:%S")
    print()
    print(_c("  FleetSafe HospitalNav Benchmark Dashboard", _BOLD, _CYAN),
          _c(f"  {ts}", _GREY))
    print(_hr())


def _section(title: str) -> None:
    print()
    print(_c(f"  {title}", _BOLD, _BLUE))
    print(_c("  " + "─" * 72, _GREY))


_AGG_COLS: list[tuple[str, str, int, bool, bool]] = [
    # (key, label, width, pct, higher_better)
    ("model",                  "Model",     8,  False, True),
    ("fleetsafe",              "FS",         3,  False, True),
    ("backend",                "Backend",   7,  False, True),
    ("n_episodes",             "N",         4,  False, True),
    ("spl_mean",               "SPL",       6,  False, True),
    ("success_rate",           "Succ%",     6,  True,  True),
    ("collision_rate",         "Coll%",     5,  True,  False),
    ("near_violation_count_mean", "NearMs", 6,  False, False),
    ("intervention_rate_mean", "Intrv%",    6,  True,  False),
    ("raw_vs_safe_delta_l2_mean", "ΔCmd",   6,  False, False),
    ("inference_latency_ms_mean", "Lat.ms", 7,  False, False),
    ("sim_fps_mean",           "FPS",       8,  False, True),
]


def _render_aggregate_table(summaries: list[dict[str, Any]]) -> None:
    _section("Aggregate Results")

    # Header row
    header = "  "
    for key, label, w, pct, _ in _AGG_COLS:
        header += _c(label.ljust(w + 1), _BOLD, _WHITE)
    print(header)
    print(_c("  " + "─" * 72, _GREY))

    # Pre-collect column values for best-highlighting
    col_vals: dict[str, list[float]] = {}
    for key, label, w, pct, _ in _AGG_COLS:
        vals = []
        for s in summaries:
            v = s.get(key)
            if isinstance(v, float) and math.isfinite(v):
                vals.append(v)
            else:
                vals.append(float("nan"))
        col_vals[key] = vals

    for i, s in enumerate(summaries):
        fs = s.get("fleetsafe", False)
        prefix = "  "
        row = prefix
        for key, label, w, pct, higher_better in _AGG_COLS:
            v = s.get(key)
            raw = col_vals[key][i]
            best = not math.isnan(raw) and _highlight_best(
                [x for x in col_vals[key] if not math.isnan(x)],
                [x for x in col_vals[key] if not math.isnan(x)].index(raw)
                if raw in col_vals[key] else -1,
                higher_better,
            )
            cell = _fmt(v, pct=pct)
            if best:
                cell = _c(cell, _BOLD, _GREEN if higher_better else _BOLD)
            if fs:
                cell = _c(cell, _CYAN) if not best else cell
            row += cell.ljust(w + 1)
        print(row)


def _render_zone_breakdown(summaries: list[dict[str, Any]]) -> None:
    if not any("steps_green_mean" in s for s in summaries):
        return
    _section("Zone Distribution  (green ██ amber ██ red)")
    for s in summaries:
        g = s.get("steps_green_mean", 0.0) or 0.0
        a = s.get("steps_amber_mean", 0.0) or 0.0
        r = s.get("steps_red_mean",   0.0) or 0.0
        total = g + a + r
        if total <= 0:
            continue
        model = s.get("model", "?")
        fs_tag = _c("✓", _CYAN) if s.get("fleetsafe") else _c("—", _GREY)
        bar = _zone_bar(g, a, r, width=24)
        pct_g = 100 * g / total
        pct_a = 100 * a / total
        pct_r = 100 * r / total
        print(f"  {model:<8} {fs_tag}  {bar}  "
              f"{_c(f'{pct_g:4.0f}%', _GREEN)} "
              f"{_c(f'{pct_a:4.0f}%', _YELLOW)} "
              f"{_c(f'{pct_r:4.0f}%', _RED)}")


def _has_social_data(s: dict[str, Any]) -> bool:
    crowd = s.get("crowding_risk_score_mean", 0) or 0
    occl  = s.get("occlusion_risk_score_mean", 0) or 0
    sviol = s.get("social_margin_violation_count_mean", 0) or 0
    mhd   = s.get("min_human_distance_m_mean", 0) or 0
    return (crowd > 0 or occl > 0 or sviol > 0) and (mhd < _INF_THRESHOLD)


def _render_social_layer(summaries: list[dict[str, Any]]) -> None:
    social = [s for s in summaries if _has_social_data(s)]
    if not social:
        return
    _section("Social Risk Layer")
    print(_c("  " + "Model    FS  Crowding  Occlusion  SocViol  MinHuman(m)", _DIM))
    for s in social:
        model = s.get("model", "?")
        fs_tag = _c("✓", _CYAN) if s.get("fleetsafe") else _c("—", _GREY)
        crowd = _fmt(s.get("crowding_risk_score_mean"), decimals=3)
        occl  = _fmt(s.get("occlusion_risk_score_mean"), decimals=3)
        sviol = _fmt(s.get("social_margin_violation_count_mean"), decimals=1)
        mhd   = _fmt(s.get("min_human_distance_m_mean"), decimals=2)
        print(f"  {model:<8} {fs_tag}  {crowd:<9} {occl:<10} {sviol:<8} {mhd}")


def _render_latency(summaries: list[dict[str, Any]]) -> None:
    _section("Latency & Throughput")
    max_lat = max((s.get("inference_latency_ms_mean", 0) or 0 for s in summaries),
                  default=1.0)
    max_lat = max(max_lat, 1.0)
    for s in summaries:
        model = s.get("model", "?")
        fs_tag = _c("✓", _CYAN) if s.get("fleetsafe") else _c("—", _GREY)
        lat = s.get("inference_latency_ms_mean", 0) or 0
        p95 = s.get("inference_latency_ms_p95_mean", 0) or 0
        fps = s.get("sim_fps_mean", 0) or 0
        bar = _sparkbar(lat, max_lat, width=12)
        lat_color = _GREEN if lat < 20 else (_YELLOW if lat < 50 else _RED)
        print(f"  {model:<8} {fs_tag}  "
              f"{_c(bar, lat_color)}  "
              f"mean={_c(f'{lat:6.1f}ms', lat_color)}  "
              f"p95={_c(f'{p95:6.1f}ms', _GREY)}  "
              f"fps={fps:>10.0f}")


def _render_footer(summaries: list[dict[str, Any]], reports_dir: Path) -> None:
    print()
    print(_hr())
    n_runs   = len(summaries)
    n_eps    = sum(int(s.get("n_episodes", 0)) for s in summaries)
    sources  = sorted({s.get("_source", "?") for s in summaries})
    print(_c(f"  {n_runs} runs  ·  {n_eps} total episodes  ·  "
             f"reports: {reports_dir}", _DIM))
    if len(sources) <= 4:
        print(_c(f"  Files: {', '.join(sources)}", _GREY))
    print()


def render_terminal(
    summaries: list[dict[str, Any]],
    reports_dir: Path,
) -> None:
    now = datetime.now()
    # Clear screen in watch mode if tty
    if sys.stdout.isatty():
        print("\033[2J\033[H", end="")
    _header(now)
    if not summaries:
        print(_c("  No results found.", _YELLOW))
        _render_footer([], reports_dir)
        return
    _render_aggregate_table(summaries)
    _render_zone_breakdown(summaries)
    _render_social_layer(summaries)
    _render_latency(summaries)
    _render_footer(summaries, reports_dir)


# ── HTML dashboard ─────────────────────────────────────────────────────────────

_HTML_STYLE = """
body{font-family:monospace;background:#0d1117;color:#c9d1d9;margin:0;padding:24px}
h1{color:#58a6ff;margin:0 0 4px}
.subtitle{color:#8b949e;font-size:.9em;margin:0 0 20px}
h2{color:#1f6feb;margin:28px 0 8px;border-bottom:1px solid #21262d;padding-bottom:4px}
table{border-collapse:collapse;width:100%;margin:8px 0;font-size:.88em}
th{background:#161b22;color:#58a6ff;padding:7px 10px;text-align:left;
   border-bottom:2px solid #21262d}
td{padding:6px 10px;border-bottom:1px solid #21262d}
tr:hover td{background:#161b22}
.fs td{background:rgba(88,166,255,.05)}
.best{color:#3fb950;font-weight:700}
.warn{color:#f85149}
.dim{color:#8b949e}
.badge-fs{background:#1f6feb;color:#fff;border-radius:3px;padding:1px 5px;font-size:.8em}
.zone-bar{height:14px;display:flex;border-radius:3px;overflow:hidden;min-width:120px}
.zone-g{background:#3fb950}
.zone-a{background:#d29922}
.zone-r{background:#f85149}
.metric-card{display:inline-block;background:#161b22;border:1px solid #21262d;
  border-radius:6px;padding:12px 18px;margin:6px;vertical-align:top;min-width:140px}
.metric-card .val{font-size:1.6em;font-weight:700;color:#58a6ff}
.metric-card .lbl{color:#8b949e;font-size:.85em}
canvas{background:#161b22;border-radius:6px;border:1px solid #21262d}
.warn-note{background:rgba(248,81,73,.1);border:1px solid #f85149;border-radius:4px;
  padding:8px 14px;margin:8px 0;color:#f85149;font-size:.85em}
"""

_HTML_SCRIPT = r"""
function drawBar(id,data){
  var c=document.getElementById(id),ctx=c.getContext('2d');
  var w=c.width,h=c.height,n=data.length,bw=w/n;
  ctx.clearRect(0,0,w,h);
  var max=Math.max.apply(null,data.map(d=>d.v||0))||1;
  data.forEach(function(d,i){
    var bh=(d.v/max)*(h-30);
    ctx.fillStyle=d.c||'#58a6ff';
    ctx.fillRect(i*bw+2,h-30-bh,bw-4,bh);
    ctx.fillStyle='#8b949e';ctx.font='10px monospace';ctx.textAlign='center';
    ctx.fillText(d.l,i*bw+bw/2,h-14);
    ctx.fillStyle='#c9d1d9';
    ctx.fillText(d.vs,i*bw+bw/2,h-30-bh-4);
  });
}
function drawScatter(id,pts){
  var c=document.getElementById(id),ctx=c.getContext('2d');
  var w=c.width,h=c.height,pad=40;
  ctx.clearRect(0,0,w,h);
  if(!pts.length){return;}
  var xs=pts.map(p=>p.x),ys=pts.map(p=>p.y);
  var xmin=Math.min.apply(null,xs),xmax=Math.max.apply(null,xs)||1;
  var ymin=Math.min.apply(null,ys),ymax=Math.max.apply(null,ys)||1;
  function px(x){return pad+(x-xmin)/(xmax-xmin||1)*(w-2*pad);}
  function py(y){return h-pad-(y-ymin)/(ymax-ymin||1)*(h-2*pad);}
  ctx.strokeStyle='#21262d';ctx.lineWidth=1;
  [0,.25,.5,.75,1].forEach(function(t){
    var y=h-pad-t*(h-2*pad);
    ctx.beginPath();ctx.moveTo(pad,y);ctx.lineTo(w-pad,y);ctx.stroke();
    ctx.fillStyle='#8b949e';ctx.font='10px monospace';ctx.textAlign='right';
    ctx.fillText((ymin+t*(ymax-ymin)).toFixed(2),pad-4,y+4);
  });
  ctx.fillStyle='#8b949e';ctx.font='10px monospace';ctx.textAlign='center';
  ctx.fillText('Intervention Rate →',w/2,h-4);
  pts.forEach(function(p){
    ctx.beginPath();
    ctx.arc(px(p.x),py(p.y),6,0,2*Math.PI);
    ctx.fillStyle=p.fs?'#58a6ff':'#8b949e';ctx.fill();
    ctx.fillStyle='#c9d1d9';ctx.font='10px monospace';ctx.textAlign='center';
    ctx.fillText(p.label,px(p.x),py(p.y)-10);
  });
  ctx.fillStyle='#58a6ff';ctx.font='11px monospace';ctx.textAlign='left';
  ctx.fillText('▲ SPL',4,14);
}
window.addEventListener('load',function(){
  if(window._barData)  drawBar('spl-bar',  window._barData);
  if(window._scatterData) drawScatter('scatter', window._scatterData);
});
"""


def _html_table(summaries: list[dict[str, Any]]) -> str:
    cols = [
        ("model",                    "Model",       False, True),
        ("fleetsafe",                "FleetSafe",   False, True),
        ("backend",                  "Backend",     False, True),
        ("n_episodes",               "N",           False, True),
        ("spl_mean",                 "SPL",         False, True),
        ("success_rate",             "Success %",   True,  True),
        ("collision_rate",           "Collision %", True,  False),
        ("near_violation_count_mean","NearMiss",    False, False),
        ("intervention_rate_mean",   "Interv. %",   True,  False),
        ("raw_vs_safe_delta_l2_mean","ΔCmd L2",     False, False),
        ("inference_latency_ms_mean","Lat. ms",     False, False),
        ("inference_latency_ms_p95_mean", "P95 ms", False, False),
        ("sim_fps_mean",             "FPS",         False, True),
    ]
    # Pre-collect best values per column
    best: dict[str, Any] = {}
    for key, _, pct, higher in cols:
        vals = [s.get(key) for s in summaries]
        nums = [v for v in vals if isinstance(v, float) and math.isfinite(v)]
        if nums:
            best[key] = max(nums) if higher else min(nums)

    rows = ""
    for s in summaries:
        fs = s.get("fleetsafe", False)
        tr_class = ' class="fs"' if fs else ""
        cells = ""
        for key, label, pct, higher in cols:
            v = s.get(key)
            if key == "fleetsafe":
                cell = '<span class="badge-fs">FS</span>' if v else '<span class="dim">—</span>'
            elif isinstance(v, float) and math.isinf(v):
                cell = '<span class="dim">∞</span>'
            elif isinstance(v, float):
                raw = f"{100*v:.1f}%" if pct else f"{v:.3f}"
                is_best = key in best and abs(v - best[key]) < 1e-9
                cell = f'<span class="best">{raw}</span>' if is_best else raw
            elif v is None:
                cell = '<span class="dim">—</span>'
            else:
                cell = str(v)
            cells += f"<td>{cell}</td>"
        rows += f"<tr{tr_class}>{cells}</tr>\n"

    heads = "".join(f"<th>{label}</th>" for _, label, _, _ in cols)
    return f"<table><thead><tr>{heads}</tr></thead><tbody>{rows}</tbody></table>"


def _html_zone_table(summaries: list[dict[str, Any]]) -> str:
    if not any("steps_green_mean" in s for s in summaries):
        return ""
    rows = ""
    for s in summaries:
        g = s.get("steps_green_mean", 0) or 0
        a = s.get("steps_amber_mean", 0) or 0
        r = s.get("steps_red_mean",   0) or 0
        total = g + a + r
        if total <= 0:
            continue
        pct_g = 100 * g / total
        pct_a = 100 * a / total
        pct_r = 100 * r / total
        bar = (f'<div class="zone-bar">'
               f'<div class="zone-g" style="width:{pct_g:.1f}%"></div>'
               f'<div class="zone-a" style="width:{pct_a:.1f}%"></div>'
               f'<div class="zone-r" style="width:{pct_r:.1f}%"></div>'
               f'</div>')
        fs_tag = '<span class="badge-fs">FS</span>' if s.get("fleetsafe") else '<span class="dim">—</span>'
        rows += (f"<tr><td>{s.get('model','?')}</td><td>{fs_tag}</td>"
                 f"<td>{bar}</td>"
                 f'<td style="color:#3fb950">{pct_g:.0f}%</td>'
                 f'<td style="color:#d29922">{pct_a:.0f}%</td>'
                 f'<td style="color:#f85149">{pct_r:.0f}%</td></tr>\n')
    if not rows:
        return ""
    return (
        "<h2>Zone Distribution</h2>"
        "<table><thead><tr><th>Model</th><th>FS</th><th>Timeline</th>"
        "<th>Green %</th><th>Amber %</th><th>Red %</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def _html_kpi_cards(summaries: list[dict[str, Any]]) -> str:
    if not summaries:
        return ""
    # Overall averages
    def _avg(key: str) -> float:
        vals = [s.get(key, 0) or 0 for s in summaries if isinstance(s.get(key), (int, float))]
        return sum(vals) / len(vals) if vals else 0.0

    n_eps   = sum(int(s.get("n_episodes", 0)) for s in summaries)
    spl     = _avg("spl_mean")
    succ    = _avg("success_rate")
    interv  = _avg("intervention_rate_mean")
    lat     = _avg("inference_latency_ms_mean")

    def card(val: str, label: str) -> str:
        return (f'<div class="metric-card">'
                f'<div class="val">{val}</div>'
                f'<div class="lbl">{label}</div></div>')

    return (
        "<h2>Summary KPIs</h2>"
        + card(str(n_eps), "Total episodes")
        + card(f"{spl:.3f}", "Mean SPL")
        + card(f"{100*succ:.1f}%", "Success rate")
        + card(f"{100*interv:.1f}%", "Interv. rate")
        + card(f"{lat:.1f} ms", "Mean latency")
    )


def _html_charts(summaries: list[dict[str, Any]]) -> str:
    # SPL bar chart data
    bar_data = []
    for s in summaries:
        fs = s.get("fleetsafe", False)
        label = f"{s.get('model','?')}{'▲' if fs else ''}"
        spl = s.get("spl_mean", 0) or 0
        color = "#58a6ff" if fs else "#8b949e"
        bar_data.append({"l": label, "v": round(spl, 4),
                         "vs": f"{spl:.3f}", "c": color})

    # Scatter: intervention_rate (x) vs SPL (y)
    scatter_data = []
    for s in summaries:
        spl = s.get("spl_mean", 0) or 0
        ir  = s.get("intervention_rate_mean", 0) or 0
        fs  = s.get("fleetsafe", False)
        label = s.get("model", "?")
        scatter_data.append({"x": round(ir, 4), "y": round(spl, 4),
                              "fs": fs, "label": label})

    bar_json     = json.dumps(bar_data)
    scatter_json = json.dumps(scatter_data)

    return f"""
<h2>Charts</h2>
<div style="display:flex;gap:16px;flex-wrap:wrap">
  <div>
    <div class="dim" style="margin-bottom:4px">SPL by model (blue = FleetSafe active)</div>
    <canvas id="spl-bar" width="480" height="200"></canvas>
  </div>
  <div>
    <div class="dim" style="margin-bottom:4px">SPL vs Intervention rate</div>
    <canvas id="scatter" width="360" height="200"></canvas>
  </div>
</div>
<script>
window._barData={bar_json};
window._scatterData={scatter_json};
</script>
"""


def render_html(
    summaries: list[dict[str, Any]],
    reports_dir: Path,
    out_path: Path | None = None,
    refresh_s: int = 0,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    n_runs = len(summaries)
    n_eps  = sum(int(s.get("n_episodes", 0)) for s in summaries)
    has_mock = any(s.get("backend") == "mock" for s in summaries)

    refresh_tag = (f'<meta http-equiv="refresh" content="{refresh_s}">'
                   if refresh_s > 0 else "")

    mock_warn = (
        '<p class="warn-note">⚠ MOCK BACKEND rows are <strong>not valid</strong> '
        'for publication claims — they use a straight-line policy with no real model.</p>'
        if has_mock else ""
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
{refresh_tag}
<title>FleetSafe HospitalNav Benchmark Dashboard — {now}</title>
<style>{_HTML_STYLE}</style>
</head>
<body>
<h1>FleetSafe HospitalNav Benchmark</h1>
<p class="subtitle">{n_runs} runs · {n_eps} episodes · generated {now}
  · source: {reports_dir}</p>
{mock_warn}
{_html_kpi_cards(summaries)}
<h2>Aggregate Results</h2>
{_html_table(summaries)}
<p class="dim">
  SPL = Success weighted by Path Length (Anderson et al. 2018) ·
  NearMiss = mean steps within near-miss threshold ·
  Interv. % = CBF interventions / total steps (FleetSafe rows only)
</p>
{_html_zone_table(summaries)}
{_html_charts(summaries)}
<script>{_HTML_SCRIPT}</script>
</body>
</html>
"""

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")
        print(f"[dashboard] HTML written → {out_path}")

    return html


# ── Entry point ────────────────────────────────────────────────────────────────

def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--reports-dir", default=str(_REPORTS_DIR),
                   help="Directory containing JSON benchmark reports")
    p.add_argument("--input", "-i", action="append", default=[],
                   metavar="FILE", help="Additional JSON file(s) to include")
    p.add_argument("--compare", metavar="FILE",
                   help="Second JSON file for side-by-side comparison")
    p.add_argument("--model",   help="Filter to this model (gnm|vint|nomad|mock)")
    p.add_argument("--scene",   help="Filter to this scene name")
    p.add_argument("--backend", help="Filter to this backend (mock|mujoco|isaaclab)")
    p.add_argument("--all-runs", action="store_true",
                   help="Show all historical runs (default: latest per model×FS×backend)")
    p.add_argument("--watch",   type=int, default=0, metavar="SECONDS",
                   help="Auto-refresh terminal view every N seconds (0=once)")
    p.add_argument("--html",    action="store_true",
                   help="Write HTML dashboard in addition to terminal output")
    p.add_argument("--html-only", action="store_true",
                   help="Write HTML and skip terminal output")
    p.add_argument("--html-out", metavar="PATH",
                   help="Path for HTML output (default: reports/dashboard.html)")
    p.add_argument("--open",    action="store_true",
                   help="Open HTML in default browser after writing")
    return p.parse_args()


def main() -> int:
    args = _parse()

    reports_dir = Path(args.reports_dir)
    extra: list[Path] = [Path(f) for f in args.input]
    if args.compare:
        extra.append(Path(args.compare))

    html_out = Path(args.html_out) if args.html_out else \
               reports_dir / "dashboard.html"

    def _run_once() -> None:
        summaries = load_reports(reports_dir, extra_files=extra)
        summaries = filter_summaries(
            summaries,
            model=args.model,
            scene=args.scene,
            backend=args.backend,
            latest=not args.all_runs,
        )

        if not args.html_only:
            render_terminal(summaries, reports_dir)

        if args.html or args.html_only:
            render_html(
                summaries,
                reports_dir,
                out_path=html_out,
                refresh_s=args.watch if args.watch > 0 else 0,
            )
            if args.open:
                import webbrowser
                webbrowser.open(html_out.as_uri())

    if args.watch > 0:
        try:
            while True:
                _run_once()
                if not args.html_only:
                    print(_c(f"  Refreshing in {args.watch}s  (Ctrl-C to stop)",
                              _GREY))
                time.sleep(args.watch)
        except KeyboardInterrupt:
            print("\n[dashboard] stopped.")
            return 0
    else:
        _run_once()

    return 0


if __name__ == "__main__":
    sys.exit(main())
