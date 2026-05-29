"""
Quota monitor — checks Gemini CLI usage before delegating heavy tasks.
Uses the stats block returned by every gemini call.
"""
import json
from pathlib import Path
from typing import Optional

# Thresholds (tune as needed)
LOW_QUOTA_THRESHOLD = 50       # requests remaining — warn and consider skipping
CRITICAL_QUOTA_THRESHOLD = 10  # hard stop — handle directly in Claude


def parse_stats(stats: dict) -> dict:
    """
    Extract useful numbers from the gemini --output-format json stats block.
    stats = data["stats"] from a gemini call response.
    """
    total_requests = 0
    total_tokens = 0
    models_used = []

    for model_name, model_data in stats.get("models", {}).items():
        api = model_data.get("api", {})
        tokens = model_data.get("tokens", {})
        total_requests += api.get("totalRequests", 0)
        total_tokens += tokens.get("total", 0)
        models_used.append(model_name)

    return {
        "total_requests_this_session": total_requests,
        "total_tokens_this_session": total_tokens,
        "models_used": models_used,
    }


def should_use_gemini(stats: Optional[dict] = None) -> bool:
    """
    Returns True if it's safe to send a heavy task to Gemini CLI.
    Pass the stats dict from a recent run_gemini() call if available.
    """
    if stats is None:
        return True  # no data — assume ok, let Gemini error on its own

    parsed = parse_stats(stats)
    session_requests = parsed["total_requests_this_session"]

    # Heuristic: if we've made many requests this session, pace ourselves
    if session_requests >= 50:
        print(f"[Nazir quota] High session usage ({session_requests} requests). Proceeding with caution.")

    # Gemini CLI doesn't expose a remaining-quota field in stats.
    # The stats block only shows what was consumed THIS session.
    # If quota is truly exhausted, gemini exits non-zero — gemini_runner raises.
    # So: always return True here; quota exhaustion surfaces as an exception.
    return True


def load_last_stats() -> Optional[dict]:
    """Load stats from the last saved gemini call (written by gemini_runner)."""
    stats_file = Path(__file__).parent.parent / "memory" / "last_gemini_stats.json"
    if stats_file.exists():
        try:
            return json.loads(stats_file.read_text())
        except json.JSONDecodeError:
            return None
    return None


def save_stats(stats: dict) -> None:
    """Persist stats from a gemini call for monitoring."""
    stats_file = Path(__file__).parent.parent / "memory" / "last_gemini_stats.json"
    stats_file.parent.mkdir(parents=True, exist_ok=True)
    stats_file.write_text(json.dumps(stats, indent=2))
