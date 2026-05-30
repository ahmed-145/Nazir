from textual.widget import Widget
from textual.app import ComposeResult
from textual.widgets import Static


class CostPanel(Widget):
    """
    Right-side top panel: $ saved this week + lifetime.
    The hero number — this is what Nazir is for.
    """

    DEFAULT_CSS = """
    CostPanel {
        height: 12;
        border: round $success;
        padding: 0 1;
    }
    CostPanel #cost-title {
        color: $success;
        text-style: bold;
        height: 1;
        margin-bottom: 1;
    }
    CostPanel #week-label {
        color: $text-muted;
        height: 1;
    }
    CostPanel #week-value {
        color: $success;
        text-style: bold;
        height: 2;
    }
    CostPanel #lifetime-label {
        color: $text-muted;
        height: 1;
    }
    CostPanel #lifetime-value {
        color: $success;
        text-style: bold;
        height: 2;
    }
    CostPanel #deleg-count {
        color: $text-muted;
        height: 1;
    }
    CostPanel #avg-latency {
        color: $text-muted;
        height: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("$ Saved",         id="cost-title")
        yield Static("This week",        id="week-label")
        yield Static("$0.0000",          id="week-value")
        yield Static("Lifetime",         id="lifetime-label")
        yield Static("$0.0000",          id="lifetime-value")
        yield Static("0 delegations",    id="deleg-count")
        yield Static("avg latency: —",   id="avg-latency")

    def refresh_data(self, costs: dict) -> None:
        self.query_one("#week-value",    Static).update(
            f"[bold green]${costs['week_dollars']:.4f}[/bold green]"
        )
        self.query_one("#lifetime-value", Static).update(
            f"[bold green]${costs['lifetime_dollars']:.4f}[/bold green]"
        )
        self.query_one("#deleg-count", Static).update(
            f"{costs['lifetime_delegations']} delegations total"
        )
        lat = costs["avg_latency_ms"]
        self.query_one("#avg-latency", Static).update(
            f"avg latency: {lat}ms" if lat else "avg latency: —"
        )
