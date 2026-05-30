#!/usr/bin/env python3
"""
Nazir Dashboard — Phase 7.

Terminal TUI showing real-time agent status, token savings, and task history.

Run:
    python3 dashboard/app.py
    python3 dashboard/app.py --export     # render and exit (for README)

Keyboard:
    q / Ctrl+C  quit
    r           force refresh
    e           export SVG snapshot
"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get(
    "NAZIR_PROJECT_ROOT",
    Path(__file__).parent.parent
)).resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer
from textual.binding import Binding

from dashboard.data import (
    heartbeat_label, heartbeat_ok, agent_status,
    session_count, active_sessions, current_task_text,
    recent_tasks_formatted, cost_summary, delegation_ratio,
)
from dashboard.widgets.status_bar  import StatusBar
from dashboard.widgets.task_panel  import TaskPanel
from dashboard.widgets.cost_panel  import CostPanel
from dashboard.widgets.token_meter import TokenMeter
from dashboard.widgets.session_panel import SessionPanel

REFRESH_INTERVAL = 2.0  # seconds


class NazirDashboard(App):
    """Nazir real-time observability dashboard."""

    TITLE = "Nazir"
    BINDINGS = [
        Binding("q",      "quit",    "Quit"),
        Binding("r",      "refresh", "Refresh"),
        Binding("e",      "export",  "Export SVG"),
        Binding("ctrl+c", "quit",    "Quit", show=False),
    ]

    DEFAULT_CSS = """
    Screen {
        background: $background;
    }
    #main-layout {
        height: 1fr;
    }
    #left-col {
        width: 2fr;
        height: 1fr;
    }
    #right-col {
        width: 1fr;
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield StatusBar(id="status-bar")
        with Horizontal(id="main-layout"):
            with Vertical(id="left-col"):
                yield TaskPanel(id="task-panel")
                yield TokenMeter(id="token-meter")
            with Vertical(id="right-col"):
                yield CostPanel(id="cost-panel")
                yield SessionPanel(id="session-panel")
        yield Footer()

    def on_mount(self) -> None:
        self._do_refresh()
        self.set_interval(REFRESH_INTERVAL, self._do_refresh)

    def _do_refresh(self) -> None:
        """Pull fresh data from all sources and push to widgets."""
        costs   = cost_summary()
        avoided, gemini_tok, ratio = delegation_ratio()
        sessions = active_sessions()

        self.query_one(StatusBar).refresh_data(
            heartbeat_label=heartbeat_label(),
            heartbeat_ok=heartbeat_ok(),
            agent_status=agent_status(),
            session_count=len(sessions),
        )
        self.query_one(TaskPanel).refresh_data(
            current_task=current_task_text(),
            recent_tasks=recent_tasks_formatted(8),
        )
        self.query_one(CostPanel).refresh_data(costs=costs)
        self.query_one(TokenMeter).refresh_data(
            claude_avoided=avoided,
            gemini_tokens=gemini_tok,
            ratio_pct=ratio,
        )
        self.query_one(SessionPanel).refresh_data(
            sessions=sessions,
            top_tasks=costs.get("top_tasks", []),
        )

    def action_refresh(self) -> None:
        self._do_refresh()

    def action_export(self) -> None:
        from dashboard.export import export_svg
        path = export_svg()
        self.notify(f"SVG saved → {path}", timeout=3)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Nazir observability dashboard")
    parser.add_argument("--export", action="store_true",
                        help="Export static snapshot and exit")
    parser.add_argument("--export-html", action="store_true",
                        help="Export static HTML snapshot and exit")
    args = parser.parse_args()

    if args.export_html:
        from dashboard.export import export_html
        path = export_html()
        print(f"HTML exported → {path}")
        return

    if args.export:
        from dashboard.export import export_svg
        path = export_svg()
        print(f"SVG exported → {path}")
        return

    app = NazirDashboard()
    app.run()


if __name__ == "__main__":
    main()
