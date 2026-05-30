"""
Nazir metrics engine — Phase 6.

Captures token usage and estimated dollar savings from every Gemini delegation.
Uses the stats block returned by every --output-format json call.

Storage: memory/metrics.db (SQLite, append-only)
Called:  automatically by gemini_runner.run_gemini() after every successful call
MCP:     cost_report() tool exposed via mcp_server/server.py
"""
import sqlite3
import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(os.environ.get(
    "NAZIR_PROJECT_ROOT",
    Path(__file__).parent.parent
)).resolve()

DB_PATH = PROJECT_ROOT / "memory" / "metrics.db"

# ── Published token pricing (per 1M tokens, USD) ──────────────────────────────
# Update these if Anthropic changes pricing.
# Source: anthropic.com/pricing (as of May 2026)
CLAUDE_OPUS_INPUT_PER_MTOK  = 15.00
CLAUDE_OPUS_OUTPUT_PER_MTOK = 75.00
CLAUDE_SONNET_INPUT_PER_MTOK  = 3.00
CLAUDE_SONNET_OUTPUT_PER_MTOK = 15.00

# Conservative estimate: we assume Sonnet-equivalent cost for avoided tokens
# (most delegation is analysis/codegen that would run on Sonnet, not Opus)
AVOIDED_COST_INPUT_PER_MTOK  = CLAUDE_SONNET_INPUT_PER_MTOK
AVOIDED_COST_OUTPUT_PER_MTOK = CLAUDE_SONNET_OUTPUT_PER_MTOK


def _db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS delegations (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp           TEXT    NOT NULL,
            task_name           TEXT,
            prompt_preview      TEXT,
            gemini_input_tokens INTEGER NOT NULL DEFAULT 0,
            gemini_output_tokens INTEGER NOT NULL DEFAULT 0,
            gemini_cached_tokens INTEGER NOT NULL DEFAULT 0,
            gemini_total_tokens INTEGER NOT NULL DEFAULT 0,
            gemini_models       TEXT,
            latency_ms          INTEGER NOT NULL DEFAULT 0,
            claude_avoided_input  INTEGER NOT NULL DEFAULT 0,
            claude_avoided_output INTEGER NOT NULL DEFAULT 0,
            dollars_saved       REAL    NOT NULL DEFAULT 0.0,
            session_id          TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_summary (
            date            TEXT PRIMARY KEY,
            delegations     INTEGER DEFAULT 0,
            gemini_tokens   INTEGER DEFAULT 0,
            dollars_saved   REAL    DEFAULT 0.0,
            updated_at      TEXT
        )
    """)
    conn.commit()
    return conn


def parse_stats(stats: dict) -> dict:
    """
    Extract token counts from the Gemini stats block.
    stats = data["stats"] from a --output-format json response.
    Returns a flat dict with totals across all models.
    """
    total_input   = 0
    total_output  = 0
    total_cached  = 0
    total_tokens  = 0
    total_latency = 0
    models_used   = []

    for model_name, model_data in stats.get("models", {}).items():
        api    = model_data.get("api",    {})
        tokens = model_data.get("tokens", {})
        total_input   += tokens.get("input",      0)
        total_output  += tokens.get("candidates", 0)
        total_cached  += tokens.get("cached",     0)
        total_tokens  += tokens.get("total",      0)
        total_latency += api.get("totalLatencyMs", 0)
        models_used.append(model_name)

    return {
        "input_tokens":   total_input,
        "output_tokens":  total_output,
        "cached_tokens":  total_cached,
        "total_tokens":   total_tokens,
        "latency_ms":     total_latency,
        "models":         models_used,
    }


def estimate_savings(
    gemini_input: int,
    gemini_output: int,
) -> tuple[int, int, float]:
    """
    Estimate how many Claude tokens this delegation avoided and what that's worth.

    We assume the same work on Claude would use:
    - The same number of input tokens (the prompt/context is the same size)
    - The same number of output tokens (same result expected)

    Returns (avoided_input, avoided_output, dollars_saved)
    """
    avoided_input  = gemini_input
    avoided_output = gemini_output
    dollars = (
        (avoided_input  / 1_000_000) * AVOIDED_COST_INPUT_PER_MTOK +
        (avoided_output / 1_000_000) * AVOIDED_COST_OUTPUT_PER_MTOK
    )
    return avoided_input, avoided_output, dollars


def record(
    stats: dict,
    task_name: Optional[str] = None,
    prompt: Optional[str] = None,
    session_id: Optional[str] = None,
) -> float:
    """
    Record one delegation event.
    Called by gemini_runner.run_gemini() after every successful call.
    Returns the dollars_saved for this call.
    """
    parsed = parse_stats(stats)
    avoided_in, avoided_out, dollars = estimate_savings(
        parsed["input_tokens"], parsed["output_tokens"]
    )

    ts = datetime.now(timezone.utc).isoformat()
    date = datetime.now().strftime("%Y-%m-%d")

    conn = _db()
    try:
        conn.execute("""
            INSERT INTO delegations (
                timestamp, task_name, prompt_preview,
                gemini_input_tokens, gemini_output_tokens, gemini_cached_tokens,
                gemini_total_tokens, gemini_models, latency_ms,
                claude_avoided_input, claude_avoided_output,
                dollars_saved, session_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            ts, task_name, (prompt or "")[:120],
            parsed["input_tokens"], parsed["output_tokens"],
            parsed["cached_tokens"], parsed["total_tokens"],
            json.dumps(parsed["models"]), parsed["latency_ms"],
            avoided_in, avoided_out, dollars, session_id,
        ))

        # Upsert daily summary
        conn.execute("""
            INSERT INTO daily_summary (date, delegations, gemini_tokens, dollars_saved, updated_at)
            VALUES (?, 1, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                delegations   = delegations + 1,
                gemini_tokens = gemini_tokens + excluded.gemini_tokens,
                dollars_saved = dollars_saved + excluded.dollars_saved,
                updated_at    = excluded.updated_at
        """, (date, parsed["total_tokens"], dollars, ts))

        conn.commit()
    finally:
        conn.close()

    return dollars


def cost_report(period: str = "week") -> dict:
    """
    Return a summary of token savings for the given period.
    period: "today" | "week" | "month" | "all"
    """
    conn = _db()
    try:
        # Date filter
        if period == "today":
            cutoff = datetime.now().strftime("%Y-%m-%d")
            where = "WHERE date(timestamp) >= ?"
            args = (cutoff,)
        elif period == "week":
            from datetime import timedelta
            cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            where = "WHERE date(timestamp) >= ?"
            args = (cutoff,)
        elif period == "month":
            from datetime import timedelta
            cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            where = "WHERE date(timestamp) >= ?"
            args = (cutoff,)
        else:  # all
            where = ""
            args = ()

        row = conn.execute(f"""
            SELECT
                COUNT(*)                         AS delegations,
                COALESCE(SUM(gemini_total_tokens), 0) AS gemini_tokens,
                COALESCE(SUM(claude_avoided_input + claude_avoided_output), 0)
                                                 AS claude_tokens_avoided,
                COALESCE(SUM(dollars_saved), 0)  AS dollars_saved,
                COALESCE(AVG(latency_ms), 0)     AS avg_latency_ms,
                MIN(timestamp)                   AS first_delegation,
                MAX(timestamp)                   AS last_delegation
            FROM delegations
            {where}
        """, args).fetchone()

        # Top tasks by savings
        top = conn.execute(f"""
            SELECT task_name, COUNT(*) as calls, SUM(dollars_saved) as saved
            FROM delegations
            {where}
            WHERE task_name IS NOT NULL
            GROUP BY task_name
            ORDER BY saved DESC
            LIMIT 5
        """, args).fetchall()

        return {
            "period":             period,
            "delegations":        row["delegations"],
            "gemini_tokens":      row["gemini_tokens"],
            "claude_tokens_avoided": row["claude_tokens_avoided"],
            "dollars_saved":      round(row["dollars_saved"], 4),
            "avg_latency_ms":     int(row["avg_latency_ms"]),
            "first_delegation":   row["first_delegation"],
            "last_delegation":    row["last_delegation"],
            "top_tasks":          [
                {"task": r["task_name"], "calls": r["calls"],
                 "saved": round(r["saved"], 4)}
                for r in top
            ],
            "pricing_model":      f"Claude Sonnet ${AVOIDED_COST_INPUT_PER_MTOK}/${ AVOIDED_COST_OUTPUT_PER_MTOK} per MTok in/out",
        }
    finally:
        conn.close()


def format_report(report: dict) -> str:
    """Human-readable cost report for MCP tool output."""
    d = report
    lines = [
        f"Nazir Cost Report — {d['period']}",
        f"{'─' * 40}",
        f"Delegations:          {d['delegations']}",
        f"Gemini tokens used:   {d['gemini_tokens']:,}",
        f"Claude tokens avoided:{d['claude_tokens_avoided']:,}",
        f"Dollars saved:        ${d['dollars_saved']:.4f}",
        f"Avg latency:          {d['avg_latency_ms']}ms",
    ]
    if d["top_tasks"]:
        lines.append(f"\nTop tasks by savings:")
        for t in d["top_tasks"]:
            lines.append(f"  {t['task']:<30} {t['calls']}x  ${t['saved']:.4f}")
    lines.append(f"\n{d['pricing_model']}")
    if d["first_delegation"]:
        lines.append(f"First delegation: {d['first_delegation'][:19]}")
    return "\n".join(lines)
