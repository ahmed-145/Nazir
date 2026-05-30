"""
Nazir Dashboard — static export.

export_svg()  — uses Textual's headless screenshot (SVG)
export_html() — renders a self-contained HTML page from live data
               (no Textual dependency — pure Python + inline CSS)

Both write to PROJECT_ROOT/dashboard/exports/ and return the path.
"""
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get(
    "NAZIR_PROJECT_ROOT",
    Path(__file__).parent.parent
)).resolve()
sys.path.insert(0, str(PROJECT_ROOT))

EXPORT_DIR = PROJECT_ROOT / "dashboard" / "exports"


def _ensure_dir() -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    return EXPORT_DIR


def export_svg(filename: str = None) -> Path:
    """
    Launch NazirDashboard headlessly, take a screenshot, save as SVG.
    Returns the output path.
    """
    from dashboard.app import NazirDashboard
    _ensure_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = filename or f"nazir_dashboard_{ts}.svg"
    out = EXPORT_DIR / filename

    app = NazirDashboard()

    async def _run():
        async with app.run_test(headless=True, size=(120, 40)) as pilot:
            await pilot.pause(0.5)   # let one refresh fire
            svg = app.export_screenshot()
            out.write_text(svg)

    import asyncio
    asyncio.run(_run())
    return out


def export_html(filename: str = None) -> Path:
    """
    Write a self-contained HTML snapshot of current dashboard data.
    No Textual dependency — works without a terminal.
    """
    from dashboard.data import full_snapshot
    _ensure_dir()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = filename or f"nazir_dashboard_{ts}.html"
    out = EXPORT_DIR / filename

    snap = full_snapshot()
    c    = snap["costs"]
    tasks = snap["recent_tasks"]

    # Build task rows
    task_rows = ""
    for t in tasks:
        icon  = "✓" if t.get("status") == "completed" else "✗"
        color = "#4caf50" if t.get("status") == "completed" else "#f44336"
        task_rows += (
            f"<tr>"
            f"<td style='color:{color};font-weight:bold'>{icon}</td>"
            f"<td>{t.get('task','')[:60]}</td>"
            f"<td style='color:#999'>{t.get('age','')}</td>"
            f"</tr>"
        )

    # Build session list
    session_html = ""
    for name, uuid in snap["sessions"].items():
        session_html += f"<li><code>{name}</code> <span style='color:#555'>{uuid[:8]}…</span></li>"
    if not session_html:
        session_html = "<li style='color:#555'>(none)</li>"

    # Build top tasks list
    top_html = ""
    for t in c.get("top_tasks", []):
        top_html += (
            f"<li>{t['task'][:30]}"
            f" <strong style='color:#4caf50'>${t['saved']:.4f}</strong>"
            f" ({t['calls']}x)</li>"
        )
    if not top_html:
        top_html = "<li style='color:#555'>(no data)</li>"

    hb_color  = "#4caf50" if snap["heartbeat_ok"] else "#f44336"
    ag_color  = "#4caf50" if snap["agent_status"] == "active" else "#ff9800"
    generated = snap["generated_at"][:19].replace("T", " ")

    total_tok = c["lifetime_gemini_tokens"] + c["lifetime_claude_avoided"]
    ratio_pct = (
        c["lifetime_gemini_tokens"] / total_tok * 100 if total_tok else 0
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nazir Dashboard — {generated}</title>
<style>
  body {{ background:#1a1a2e; color:#e0e0e0; font-family:monospace;
         margin:0; padding:20px; }}
  h1   {{ color:#7986cb; margin:0 0 4px 0; }}
  .subtitle {{ color:#555; margin-bottom:20px; font-size:12px; }}
  .grid {{ display:grid; grid-template-columns:2fr 1fr; gap:16px; }}
  .card {{ background:#16213e; border-radius:8px; padding:16px;
           border:1px solid #333; }}
  .card h2 {{ margin:0 0 12px 0; font-size:14px; }}
  .green {{ color:#4caf50; }} .red {{ color:#f44336; }}
  .yellow {{ color:#ff9800; }} .cyan {{ color:#00bcd4; }}
  .muted {{ color:#666; }}
  .hero {{ font-size:28px; font-weight:bold; color:#4caf50; }}
  .status-bar {{ display:flex; gap:24px; background:#0f3460;
                 border-radius:6px; padding:8px 16px;
                 margin-bottom:16px; font-size:13px; }}
  table {{ width:100%; border-collapse:collapse; font-size:12px; }}
  td    {{ padding:4px 8px; border-bottom:1px solid #222; }}
  ul    {{ margin:4px 0; padding-left:20px; font-size:12px; line-height:1.8; }}
  .bar-track {{ background:#222; border-radius:4px; height:8px; margin-top:8px; }}
  .bar-fill  {{ background:#00bcd4; border-radius:4px; height:8px; }}
</style>
</head>
<body>
<h1>Nazir Dashboard</h1>
<div class="subtitle">Generated: {generated} &nbsp;|&nbsp; Live snapshot</div>

<div class="status-bar">
  <span>⬤ heartbeat: <span style="color:{hb_color}">{snap['heartbeat_label']}</span></span>
  <span>claude-agent: <span style="color:{ag_color}">{snap['agent_status']}</span></span>
  <span class="muted">gemini sessions: {snap['session_count']}</span>
</div>

<div class="grid">
  <!-- Left column -->
  <div>
    <div class="card" style="margin-bottom:16px">
      <h2 class="cyan">Active Task</h2>
      <div>{'<strong>' + snap['current_task'][:200] + '</strong>' if snap['current_task'] else '<span class="muted">(idle)</span>'}</div>
    </div>

    <div class="card" style="margin-bottom:16px">
      <h2 class="cyan">Token Meter — lifetime</h2>
      <div><span class="yellow">Claude avoided:</span> {c['lifetime_claude_avoided']:,} tokens</div>
      <div><span class="cyan">Gemini used:</span>     {c['lifetime_gemini_tokens']:,} tokens</div>
      <div style="margin-top:8px" class="muted">Delegation ratio: <strong style="color:#e0e0e0">{ratio_pct:.1f}%</strong> routed to Gemini</div>
      <div class="bar-track">
        <div class="bar-fill" style="width:{min(ratio_pct,100):.1f}%"></div>
      </div>
    </div>

    <div class="card">
      <h2 class="cyan">Recent Tasks</h2>
      <table>{'<tbody>' + task_rows + '</tbody>' if task_rows else '<tr><td class="muted">(no history)</td></tr>'}</table>
    </div>
  </div>

  <!-- Right column -->
  <div>
    <div class="card" style="margin-bottom:16px">
      <h2 class="green">$ Saved</h2>
      <div class="muted" style="font-size:12px">This week</div>
      <div class="hero">${c['week_dollars']:.4f}</div>
      <div class="muted" style="font-size:12px;margin-top:12px">Lifetime</div>
      <div class="hero">${c['lifetime_dollars']:.4f}</div>
      <div class="muted" style="font-size:12px;margin-top:8px">
        {c['lifetime_delegations']} delegations &nbsp;|&nbsp;
        avg {c['avg_latency_ms']}ms
      </div>
    </div>

    <div class="card" style="margin-bottom:16px">
      <h2 class="cyan">Sessions</h2>
      <ul>{session_html}</ul>
    </div>

    <div class="card">
      <h2 class="cyan">Top Tasks by Savings</h2>
      <ul>{top_html}</ul>
    </div>
  </div>
</div>
</body>
</html>"""

    out.write_text(html)
    return out
