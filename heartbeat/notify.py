"""
Desktop notifications for the heartbeat daemon.
Uses gdbus (GNOME) with notifypy as fallback.
"""
import subprocess
import os


def notify(title: str, body: str, urgency: str = "normal") -> None:
    """
    Send a desktop notification.
    urgency: "low" | "normal" | "critical"
    """
    # Try gdbus first (works in GNOME Wayland without libnotify-bin)
    try:
        subprocess.run([
            "gdbus", "call", "--session",
            "--dest", "org.freedesktop.Notifications",
            "--object-path", "/org/freedesktop/Notifications",
            "--method", "org.freedesktop.Notifications.Notify",
            "Nazir",          # app-name
            "0",              # replaces-id
            "dialog-warning", # icon
            title,
            body,
            "[]",             # actions
            '{"urgency": <byte 2>}' if urgency == "critical" else "{}",
            "10000",          # timeout ms
        ], capture_output=True, timeout=5,
           env={**os.environ, "DBUS_SESSION_BUS_ADDRESS": _dbus_addr()})
        return
    except Exception:
        pass

    # Fallback: notifypy
    try:
        from notifypy import Notify
        n = Notify()
        n.title = f"Nazir — {title}"
        n.message = body
        n.send()
        return
    except Exception:
        pass

    # Last resort: print to terminal
    print(f"[Nazir NOTIFY] {title}: {body}")


def _dbus_addr() -> str:
    """Get the D-Bus session bus address for the current user."""
    addr = os.environ.get("DBUS_SESSION_BUS_ADDRESS", "")
    if addr:
        return addr
    # Try to find it from the running session
    try:
        result = subprocess.run(
            ["bash", "-c",
             "cat /proc/$(pgrep -u $USER gnome-session | head -1)/environ 2>/dev/null "
             "| tr '\\0' '\\n' | grep DBUS_SESSION_BUS_ADDRESS | cut -d= -f2-"],
            capture_output=True, text=True, timeout=3
        )
        return result.stdout.strip() or addr
    except Exception:
        return addr
