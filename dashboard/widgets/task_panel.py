from textual.widget import Widget
from textual.app import ComposeResult
from textual.widgets import Static
from textual.containers import ScrollableContainer


class TaskPanel(Widget):
    """
    Left-side panel: current task + recent task history.
    """

    DEFAULT_CSS = """
    TaskPanel {
        height: 1fr;
        border: round $primary;
        padding: 0 1;
    }
    TaskPanel #task-title {
        color: $primary;
        text-style: bold;
        height: 1;
        margin-bottom: 1;
    }
    TaskPanel #current-task {
        color: $text;
        height: auto;
        margin-bottom: 1;
    }
    TaskPanel #divider {
        color: $text-muted;
        height: 1;
    }
    TaskPanel ScrollableContainer {
        height: 1fr;
    }
    TaskPanel .task-row {
        height: 1;
    }
    TaskPanel .task-ok {
        color: $success;
    }
    TaskPanel .task-fail {
        color: $error;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Active Task", id="task-title")
        yield Static("(idle)", id="current-task")
        yield Static("─" * 50, id="divider")
        with ScrollableContainer():
            yield Static("", id="recent-tasks-body")

    def refresh_data(self, current_task: str, recent_tasks: list[dict]) -> None:
        ct = self.query_one("#current-task", Static)
        if current_task:
            # Truncate long tasks gracefully
            display = current_task[:200] if len(current_task) > 200 else current_task
            ct.update(f"[bold]{display}[/bold]")
        else:
            ct.update("[dim](idle — no active task)[/dim]")

        body = self.query_one("#recent-tasks-body", Static)
        if not recent_tasks:
            body.update("[dim]No task history yet[/dim]")
            return

        lines = []
        for t in recent_tasks:
            icon  = "✓" if t.get("status") == "completed" else "✗"
            color = "green" if t.get("status") == "completed" else "red"
            task  = (t.get("task") or "")[:38]
            age   = t.get("age", "?")
            lines.append(f"[{color}]{icon}[/{color}]  {task:<40} [{age}]")

        body.update("\n".join(lines))
