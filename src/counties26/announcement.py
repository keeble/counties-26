"""Prepare the end-of-event winner announcement."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from counties26.constants import require_division
from counties26.standings import ranked_team_rows


@dataclass(frozen=True)
class AnnouncementTeam:
    division: str
    place: int
    team_name: str
    total_points: float
    total_pinfall: int
    players: tuple[str, ...]
    points_behind_above: float | None
    points_ahead_of_below: float | None


def _ranked_teams(conn: sqlite3.Connection, division: str) -> list[sqlite3.Row]:
    return ranked_team_rows(conn, division)


def announcement_teams(
    conn: sqlite3.Connection, division: str
) -> list[AnnouncementTeam]:
    """Return all teams in ranked order with roster names and adjacent gaps."""
    require_division(division)
    rows = _ranked_teams(conn, division)
    teams: list[AnnouncementTeam] = []
    for index, row in enumerate(rows):
        above = rows[index - 1]["total_points"] if index else None
        below = rows[index + 1]["total_points"] if index + 1 < len(rows) else None
        players = conn.execute(
            "SELECT name FROM players WHERE team_id = ? ORDER BY play_position",
            (row["team_id"],),
        ).fetchall()
        if not players:
            # A legacy database may predate roster import; still make the command useful.
            players = conn.execute(
                """
                SELECT DISTINCT bowler_name AS name
                FROM bowler_scores
                WHERE team_id = ?
                ORDER BY name
                """,
                (row["team_id"],),
            ).fetchall()
        teams.append(
            AnnouncementTeam(
                division=division,
                place=index + 1,
                    team_name=row["team_name"],
                total_points=row["total_points"],
                total_pinfall=row["total_pinfall"],
                players=tuple(player["name"] for player in players),
                points_behind_above=(above - row["total_points"]) if above is not None else None,
                points_ahead_of_below=(row["total_points"] - below) if below is not None else None,
            )
        )
    return teams


def announcement_order(conn: sqlite3.Connection) -> list[AnnouncementTeam]:
    """Return women/men in the requested PA reveal order."""
    ranked = {
        division: announcement_teams(conn, division)
        for division in ("women", "men")
    }
    ordered: list[AnnouncementTeam] = []
    for place in (3, 2, 1):
        for division in ("women", "men"):
            teams = ranked[division]
            if len(teams) >= place:
                ordered.append(teams[place - 1])
    return ordered


def format_announcement(conn: sqlite3.Connection) -> str:
    """Format the PA-ready announcement in reveal order."""
    lines = ["WINNER ANNOUNCEMENT", "===================", ""]
    for team in announcement_order(conn):
        lines.append(f"{team.place}{_ordinal_suffix(team.place)} place {team.division}")
        lines.append(f"{team.team_name} — {team.total_points:g} points")
        lines.append(f"Pinfall: {team.total_pinfall}")
        lines.append("Players: " + (", ".join(team.players) if team.players else "not registered"))
        above = "n/a" if team.points_behind_above is None else f"{team.points_behind_above:g} behind the team above"
        below = "n/a" if team.points_ahead_of_below is None else f"{team.points_ahead_of_below:g} ahead of the team below"
        lines.append(f"Gap: {above}; {below}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _ordinal_suffix(place: int) -> str:
    if place % 100 in (11, 12, 13):
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(place % 10, "th")