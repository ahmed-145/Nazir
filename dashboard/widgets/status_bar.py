from textual.widget import Widget
from textual.app import ComposeResult
from textual.widgets import Static
from textual.reactive import reactive


class StatusBar(Widget):
    """
    Top status line: heartbeat age · agent service · sessions count.
    Updates every refresh cycle via update() call from the main app.
    """

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: $panel;
        padding: 0 1;
    }
    StatusBar Static {
        width: 1fr;
    }
    StatusBar #hb-label {
        color: $success;
    }
    StatusBar #hb-label.stale {
        color: $error;
    }
    StatusBar #agent-label {
        color: $success;
    }
    StatusBar #agent-label.inactive {
        color: $warning;
    }
    StatusBar #session-label {
        color: $text-muted;
        text-align: right;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("⬤ heartbeat: …", id="hb-label")
        yield Static("agent: …",       id="agent-label")
        yield Static("sessions: …",    id="session-label")

    def refresh_data(
        self,
        heartbeat_label: str,
        heartbeat_ok: bool,
        agent_status: str,
        session_count: int,
    ) -> None:
        hb = self.query_one("#hb-label", Static)
        hb.update(f"⬤ heartbeat: {heartbeat_label}")
        hb.set_class(not heartbeat_ok, "stale")

        ag = self.query_one("#agent-label", Static)
        ag.update(f"claude-agent: {agent_status}")
        ag.set_class(agent_status != "active", "inactive")

        sl = self.query_one("#session-label", Static)
        sl.update(f"gemini sessions: {session_count}")
