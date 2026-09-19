"""Queries and small view models used by the static site generator."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from counties26.scoring import compute_individual_points
from counties26.standings import bowler_stats, team_standings


@dataclass(frozen=True)
class PlayerMatchup:
    position: int
    team_a_bowler: str
    team_a_score: int | None
    team_b_bowler: str
    team_b_score: int | None
    team_a_bonus: float | None
    team_b_bonus: float | None


@dataclass(frozen=True)
class FixtureView:
    fixture_id: int
    round_number: int
    lane_a: int
    lane_b: int
    team_a_id: int
    team_a_name: str
    team_b_id: int
    team_b_name: str
    team_a_pinfall: int | None
    team_b_pinfall: int | None
    team_a_points: float | None
    team_b_points: float | None
    matchups: list[PlayerMatchup]

    @property
    def complete(self) -> bool:
        return bool(self.matchups) and all(
            matchup.team_a_score is not None and matchup.team_b_score is not None
            for matchup in self.matchups
        )


def team_slug(team_id: int, team_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", team_name.lower()).strip("-")
    return f"team-{team_id}-{slug or 'team'}"


def _score_rows(conn: sqlite3.Connection, fixture_id: int, team_id: int) -> dict[int, sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT play_position, bowler_name, scratch_score
        FROM bowler_scores
        WHERE fixture_id = ? AND team_id = ?
        ORDER BY play_position
        """,
        (fixture_id, team_id),
    ).fetchall()
    return {row["play_position"]: row for row in rows}


def _fixture_view(conn: sqlite3.Connection, row: sqlite3.Row) -> FixtureView:
    scores_a = _score_rows(conn, row["fixture_id"], row["team_a_id"])
    scores_b = _score_rows(conn, row["fixture_id"], row["team_b_id"])
    positions = sorted(set(scores_a) | set(scores_b))
    matchups: list[PlayerMatchup] = []
    for position in positions:
        player_a = scores_a.get(position)
        player_b = scores_b.get(position)
        score_a = player_a["scratch_score"] if player_a else None
        score_b = player_b["scratch_score"] if player_b else None
        bonus_a = bonus_b = None
        if score_a is not None and score_b is not None:
            bonus_a, bonus_b = compute_individual_points(score_a, score_b)
        matchups.append(
            PlayerMatchup(
                position=position,
                team_a_bowler=player_a["bowler_name"] if player_a else "Missing",
                team_a_score=score_a,
                team_b_bowler=player_b["bowler_name"] if player_b else "Missing",
                team_b_score=score_b,
                team_a_bonus=bonus_a,
                team_b_bonus=bonus_b,
            )
        )
    return FixtureView(
        fixture_id=row["fixture_id"],
        round_number=row["round_number"],
        lane_a=row["lane_a"],
        lane_b=row["lane_b"],
        team_a_id=row["team_a_id"],
        team_a_name=row["team_a_name"],
        team_b_id=row["team_b_id"],
        team_b_name=row["team_b_name"],
        team_a_pinfall=row["team_a_pinfall"],
        team_b_pinfall=row["team_b_pinfall"],
        team_a_points=row["team_a_points"],
        team_b_points=row["team_b_points"],
        matchups=matchups,
    )


def _fixtures(conn: sqlite3.Connection, division: str) -> list[FixtureView]:
    rows = conn.execute(
        """
        SELECT f.id AS fixture_id, r.round_number, f.lane_a, f.lane_b,
               ta.id AS team_a_id, ta.name AS team_a_name,
               tb.id AS team_b_id, tb.name AS team_b_name,
               mpa.pinfall_total AS team_a_pinfall,
               mpb.pinfall_total AS team_b_pinfall,
               mpa.total_points AS team_a_points,
               mpb.total_points AS team_b_points
        FROM fixtures f
        JOIN rounds r ON r.id = f.round_id
        JOIN teams ta ON ta.id = f.team_a_id
        JOIN teams tb ON tb.id = f.team_b_id
        LEFT JOIN match_points mpa ON mpa.fixture_id = f.id AND mpa.team_id = ta.id
        LEFT JOIN match_points mpb ON mpb.fixture_id = f.id AND mpb.team_id = tb.id
        WHERE r.division = ?
        ORDER BY r.round_number, f.lane_a
        """,
        (division,),
    ).fetchall()
    return [_fixture_view(conn, row) for row in rows]


def division_page_data(conn: sqlite3.Connection, division: str) -> dict[str, object]:
    standings = team_standings(conn, division)
    standing_by_name = {standing.team_name: standing for standing in standings}
    teams = conn.execute(
        "SELECT id, name FROM teams WHERE division = ? ORDER BY name", (division,)
    ).fetchall()
    team_links = {
        row["id"]: {"name": row["name"], "href": f"{team_slug(row['id'], row['name'])}.html"}
        for row in teams
    }
    team_id_by_name = {row["name"]: row["id"] for row in teams}
    linked_standings = []
    for standing in standings:
        linked_standings.append(
            {
                "team_name": standing.team_name,
                "played": standing.played,
                "total_points": standing.total_points,
                "total_pinfall": standing.total_pinfall,
                "href": team_links[team_id_by_name[standing.team_name]]["href"],
            }
        )
    fixtures = _fixtures(conn, division)
    return {
        "standings": linked_standings,
        "bowlers": bowler_stats(conn, division),
        "fixtures": fixtures,
        "team_links": team_links,
    }


def team_page_data(conn: sqlite3.Connection, team_id: int) -> dict[str, object]:
    team = conn.execute("SELECT id, name, division FROM teams WHERE id = ?", (team_id,)).fetchone()
    if team is None:
        raise ValueError(f"No such team: {team_id}")
    division_data = division_page_data(conn, team["division"])
    fixtures = [
        fixture
        for fixture in division_data["fixtures"]
        if team_id in (fixture.team_a_id, fixture.team_b_id)
    ]
    team_bowlers = [
        stat for stat in division_data["bowlers"] if stat.team_name == team["name"]
    ]
    roster = conn.execute(
        """
        SELECT play_position, name
        FROM players
        WHERE team_id = ?
        ORDER BY play_position
        """,
        (team_id,),
    ).fetchall()
    standing = next(
        standing for standing in division_data["standings"] if standing["team_name"] == team["name"]
    )
    return {
        "team": team,
        "standing": standing,
        "bowlers": team_bowlers,
        "roster": roster,
        "fixtures": fixtures,
        "team_links": division_data["team_links"],
    }