"""Recompute persisted match points from raw bowler scores.

``match_points`` is fully derived — always deleted and recomputed for a fixture rather
than patched, so corrections and re-imports can never leave stale numbers behind.
"""

from __future__ import annotations

import sqlite3

from counties26.scoring import compute_fixture_result


def recompute_fixture(conn: sqlite3.Connection, fixture_id: int) -> str | None:
    """Recompute match_points for one fixture. Returns a warning message if it
    couldn't be scored (e.g. incomplete lineup), or None on success."""
    fixture = conn.execute(
        """
        SELECT f.team_a_id, f.team_b_id, ta.team_size AS team_size, ta.division AS division
        FROM fixtures f
        JOIN teams ta ON ta.id = f.team_a_id
        WHERE f.id = ?
        """,
        (fixture_id,),
    ).fetchone()
    if fixture is None:
        raise ValueError(f"No such fixture: {fixture_id}")

    team_bonus = _team_bonus_for_division(conn, fixture["division"])

    team_a_scores = _ordered_scores(conn, fixture_id, fixture["team_a_id"])
    team_b_scores = _ordered_scores(conn, fixture_id, fixture["team_b_id"])

    conn.execute("DELETE FROM match_points WHERE fixture_id = ?", (fixture_id,))

    if not team_a_scores or not team_b_scores:
        conn.commit()
        return f"Fixture {fixture_id}: no scores recorded yet for one or both teams — skipped"
    if len(team_a_scores) != len(team_b_scores) or len(team_a_scores) != fixture["team_size"]:
        conn.commit()
        return (
            f"Fixture {fixture_id}: incomplete lineup "
            f"({len(team_a_scores)} vs {len(team_b_scores)} bowlers, expected "
            f"{fixture['team_size']} each) — scoring skipped until resolved"
        )

    result = compute_fixture_result(team_a_scores, team_b_scores, team_bonus)

    conn.execute(
        """
        INSERT INTO match_points (fixture_id, team_id, pinfall_total, bonus_points, team_bonus, total_points)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            fixture_id,
            fixture["team_a_id"],
            result.team_a_pinfall,
            sum(result.team_a_bonus_points),
            result.team_a_team_bonus,
            result.team_a_total,
        ),
    )
    conn.execute(
        """
        INSERT INTO match_points (fixture_id, team_id, pinfall_total, bonus_points, team_bonus, total_points)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            fixture_id,
            fixture["team_b_id"],
            result.team_b_pinfall,
            sum(result.team_b_bonus_points),
            result.team_b_team_bonus,
            result.team_b_total,
        ),
    )
    conn.commit()
    return None


def _team_bonus_for_division(conn: sqlite3.Connection, division: str) -> float:
    from counties26.constants import DIVISION_CONFIG

    return DIVISION_CONFIG[division].team_bonus


def _ordered_scores(conn: sqlite3.Connection, fixture_id: int, team_id: int) -> list[int]:
    rows = conn.execute(
        """
        SELECT scratch_score FROM bowler_scores
        WHERE fixture_id = ? AND team_id = ?
        ORDER BY play_position
        """,
        (fixture_id, team_id),
    ).fetchall()
    return [row["scratch_score"] for row in rows]
