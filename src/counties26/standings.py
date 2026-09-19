"""Read-only aggregation queries. Nothing here is persisted — always computed live
from ``match_points`` and ``bowler_scores`` so it can never go stale."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class TeamStanding:
    team_name: str
    played: int
    total_points: float
    total_pinfall: int


@dataclass(frozen=True)
class BowlerStat:
    team_name: str
    bowler_name: str
    games_played: int
    average: float
    high_score: int


def team_standings(conn: sqlite3.Connection, division: str) -> list[TeamStanding]:
    rows = ranked_team_rows(conn, division)
    return [
        TeamStanding(
            team_name=row["team_name"],
            played=row["played"],
            total_points=int(row["total_points"]),
            total_pinfall=row["total_pinfall"],
        )
        for row in rows
    ]


def ranked_team_rows(conn: sqlite3.Connection, division: str) -> list[sqlite3.Row]:
    """Return team rows ranked with head-to-head tie-breaking."""
    rows = conn.execute(
        """
        SELECT t.id AS team_id, t.name AS team_name,
               COUNT(mp.id) AS played,
               COALESCE(SUM(mp.total_points), 0) AS total_points,
               COALESCE(SUM(mp.pinfall_total), 0) AS total_pinfall
        FROM teams t
        LEFT JOIN match_points mp ON mp.team_id = t.id
        WHERE t.division = ?
        GROUP BY t.id
        """,
        (division,),
    ).fetchall()
    rows = sorted(
        rows,
        key=lambda row: (-row["total_points"], -row["total_pinfall"], row["team_name"]),
    )
    ranked: list[sqlite3.Row] = []
    index = 0
    while index < len(rows):
        end = index + 1
        while end < len(rows) and rows[end]["total_points"] == rows[index]["total_points"]:
            end += 1
        group = list(rows[index:end])
        tied_ids = {row["team_id"] for row in group}
        group.sort(
            key=lambda row: (
                -_head_to_head_points(conn, row["team_id"], tied_ids),
                -row["total_pinfall"],
                row["team_name"],
            )
        )
        ranked.extend(group)
        index = end
    return ranked


def _head_to_head_points(
    conn: sqlite3.Connection, team_id: int, tied_team_ids: set[int]
) -> float:
    """Sum a team's persisted match points against teams in its tied group."""
    opponents = tuple(opponent for opponent in tied_team_ids if opponent != team_id)
    if not opponents:
        return 0.0
    placeholders = ",".join("?" for _ in opponents)
    row = conn.execute(
        f"""
        SELECT COALESCE(SUM(mp.total_points), 0) AS points
        FROM match_points mp
        JOIN fixtures f ON f.id = mp.fixture_id
        WHERE mp.team_id = ?
          AND (f.team_a_id IN ({placeholders}) OR f.team_b_id IN ({placeholders}))
        """,
        (team_id, *opponents, *opponents),
    ).fetchone()
    return row["points"]


def bowler_stats(conn: sqlite3.Connection, division: str) -> list[BowlerStat]:
    rows = conn.execute(
        """
        SELECT t.name AS team_name,
               bs.bowler_name AS bowler_name,
               COUNT(*) AS games_played,
               AVG(bs.scratch_score) AS average,
               MAX(bs.scratch_score) AS high_score
        FROM bowler_scores bs
        JOIN teams t ON t.id = bs.team_id
        WHERE t.division = ?
        GROUP BY t.id, bs.bowler_name
        ORDER BY average DESC
        """,
        (division,),
    ).fetchall()
    return [
        BowlerStat(
            team_name=row["team_name"],
            bowler_name=row["bowler_name"],
            games_played=row["games_played"],
            average=round(row["average"], 1),
            high_score=row["high_score"],
        )
        for row in rows
    ]
