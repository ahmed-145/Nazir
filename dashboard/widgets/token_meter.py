from textual.widget import Widget
from textual.app import ComposeResult
from textual.widgets import Static, ProgressBar


class TokenMeter(Widget):
    """
    Token delegation meter: Claude avoided vs Gemini used, ratio bar.
    """

    DEFAULT_CSS = """
    TokenMeter {
        height: 8;
        border: round $primary;
        padding: 0 1;
    }
    TokenMeter #meter-title {
        color: $primary;
        text-style: bold;
        height: 1;
        margin-bottom: 1;
    }
    TokenMeter #claude-line {
        height: 1;
        color: $warning;
    }
    TokenMeter #gemini-line {
        height: 1;
        color: $accent;
    }
    TokenMeter #ratio-label {
        height: 1;
        color: $text-muted;
        margin-top: 1;
    }
    TokenMeter ProgressBar {
        height: 1;
    }
    TokenMeter ProgressBar > .bar--bar {
        color: $accent;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Token Meter — lifetime", id="meter-title")
        yield Static("Claude:  0 tokens  (decisions + review)", id="claude-line")
        yield Static("Gemini:  0 tokens  (analysis + codegen)", id="gemini-line")
        yield Static("Delegation ratio: 0%", id="ratio-label")
        yield ProgressBar(total=100, show_eta=False, show_percentage=False)

    def refresh_data(
        self,
        claude_avoided: int,
        gemini_tokens: int,
        ratio_pct: float,
    ) -> None:
        self.query_one("#claude-line", Static).update(
            f"[yellow]Claude:[/yellow]  {claude_avoided:>10,} tokens  "
            f"(decisions + review)"
        )
        self.query_one("#gemini-line", Static).update(
            f"[cyan]Gemini:[/cyan]  {gemini_tokens:>10,} tokens  "
            f"(analysis + codegen)"
        )
        self.query_one("#ratio-label", Static).update(
            f"Delegation ratio: [bold]{ratio_pct:.1f}%[/bold] routed to Gemini"
        )
        pb = self.query_one(ProgressBar)
        pb.update(progress=ratio_pct)
