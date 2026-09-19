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
    rows = conn.execute(
        """
        SELECT t.name AS team_name,
               COUNT(mp.id) AS played,
               COALESCE(SUM(mp.total_points), 0) AS total_points,
               COALESCE(SUM(mp.pinfall_total), 0) AS total_pinfall
        FROM teams t
        LEFT JOIN match_points mp ON mp.team_id = t.id
        WHERE t.division = ?
        GROUP BY t.id
        ORDER BY total_points DESC, total_pinfall DESC, team_name ASC
        """,
        (division,),
    ).fetchall()
    return [
        TeamStanding(
            team_name=row["team_name"],
            played=row["played"],
            total_points=row["total_points"],
            total_pinfall=row["total_pinfall"],
        )
        for row in rows
    ]


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
