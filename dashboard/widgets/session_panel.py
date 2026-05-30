from textual.widget import Widget
from textual.app import ComposeResult
from textual.widgets import Static


class SessionPanel(Widget):
    """
    Right-side bottom panel: active Gemini session names + top tasks by savings.
    """

    DEFAULT_CSS = """
    SessionPanel {
        height: 1fr;
        border: round $accent;
        padding: 0 1;
    }
    SessionPanel #session-title {
        color: $accent;
        text-style: bold;
        height: 1;
        margin-bottom: 1;
    }
    SessionPanel #session-body {
        height: auto;
        color: $text;
    }
    SessionPanel #top-title {
        color: $accent;
        text-style: bold;
        height: 1;
        margin-top: 1;
        margin-bottom: 0;
    }
    SessionPanel #top-body {
        height: 1fr;
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Sessions",   id="session-title")
        yield Static("(none)",     id="session-body")
        yield Static("Top Tasks",  id="top-title")
        yield Static("(none)",     id="top-body")

    def refresh_data(self, sessions: dict, top_tasks: list[dict]) -> None:
        sb = self.query_one("#session-body", Static)
        if sessions:
            lines = [
                f"[cyan]{name}[/cyan]  [dim]{uuid[:8]}…[/dim]"
                for name, uuid in sessions.items()
            ]
            sb.update("\n".join(lines))
        else:
            sb.update("[dim](no active sessions)[/dim]")

        tb = self.query_one("#top-body", Static)
        if top_tasks:
            lines = [
                f"{t['task'][:24]:<26} [green]${t['saved']:.4f}[/green]"
                for t in top_tasks
            ]
            tb.update("\n".join(lines))
        else:
            tb.update("[dim](no data yet)[/dim]")
