"""Import an organizer-supplied lane draw (grid + team registry) into the database.

Grid format (confirmed against a worked 10-team example): no header row or column.
Each row is one round; column position (1-indexed) is the lane number; the cell value
is the team number occupying that lane for that round. Adjacent lane pairs (1&2, 3&4,
...) form that round's fixtures. For N teams there are N-1 rounds in a complete single
round robin.
"""

from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from counties26.constants import DIVISION_CONFIG, require_division


@dataclass(frozen=True)
class TeamInfo:
    team_number: int
    name: str
    team_size: int


@dataclass(frozen=True)
class PlayerInfo:
    team_number: int
    play_position: int
    name: str


def parse_grid(path: str | Path) -> list[list[int]]:
    """Parse the lane draw grid: one row per round, one column per lane."""
    rows: list[list[int]] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        for raw_row in reader:
            values = [cell.strip() for cell in raw_row if cell.strip() != ""]
            if not values:
                continue
            rows.append([int(v) for v in values])
    return rows


def parse_team_registry(path: str | Path, default_team_size: int) -> dict[int, TeamInfo]:
    """Parse team_number,team_name[,team_size] -> TeamInfo, keyed by team_number."""
    teams: dict[int, TeamInfo] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            team_number = int(row["team_number"])
            name = row["team_name"].strip()
            size_field = (row.get("team_size") or "").strip()
            team_size = int(size_field) if size_field else default_team_size
            teams[team_number] = TeamInfo(team_number=team_number, name=name, team_size=team_size)
    return teams


def parse_player_registry(path: str | Path) -> list[PlayerInfo]:
    """Parse team_number,play_position,player_name rows for the starting roster."""
    players: list[PlayerInfo] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            players.append(
                PlayerInfo(
                    team_number=int(row["team_number"]),
                    play_position=int(row["play_position"]),
                    name=row["player_name"].strip(),
                )
            )
    return players


def validate_round_robin(rows: list[list[int]]) -> list[str]:
    """Sanity-check the grid. Returns a list of human-readable warnings (empty if clean)."""
    warnings: list[str] = []
    if not rows:
        return ["Draw grid is empty"]

    lane_count = len(rows[0])
    expected_teams = set(rows[0])
    if lane_count % 2 != 0:
        warnings.append(f"Grid has an odd number of lanes ({lane_count}); lanes must pair up")

    seen_pairs: dict[frozenset[int], int] = {}
    for round_number, row in enumerate(rows, start=1):
        if len(row) != lane_count:
            warnings.append(
                f"Round {round_number} has {len(row)} lanes, expected {lane_count}"
            )
            continue
        if set(row) != expected_teams or len(set(row)) != len(row):
            warnings.append(
                f"Round {round_number} does not contain every team exactly once"
            )
            continue
        for i in range(0, lane_count, 2):
            pair = frozenset((row[i], row[i + 1]))
            if pair in seen_pairs:
                warnings.append(
                    f"Teams {tuple(pair)} meet more than once "
                    f"(rounds {seen_pairs[pair]} and {round_number})"
                )
            seen_pairs[pair] = round_number

    n_teams = len(expected_teams)
    if len(rows) != n_teams - 1:
        warnings.append(
            f"Expected {n_teams - 1} rounds for a complete round robin of {n_teams} teams, "
            f"got {len(rows)}"
        )
    expected_pairs = n_teams * (n_teams - 1) // 2
    if len(seen_pairs) != expected_pairs:
        warnings.append(
            f"Only {len(seen_pairs)} of {expected_pairs} possible team pairings are present "
            "— the draw does not look like a complete round robin"
        )
    return warnings


def import_draw(
    conn: sqlite3.Connection,
    grid_path: str | Path,
    teams_path: str | Path,
    division: str,
    players_path: str | Path | None = None,
) -> list[str]:
    """Import a division's draw. Returns validation warnings (import still proceeds)."""
    require_division(division)
    default_team_size = DIVISION_CONFIG[division].team_size

    rows = parse_grid(grid_path)
    teams = parse_team_registry(teams_path, default_team_size)
    players = parse_player_registry(players_path) if players_path else []
    warnings = validate_round_robin(rows)

    team_numbers_in_grid = {t for row in rows for t in row}
    missing_from_registry = team_numbers_in_grid - set(teams)
    if missing_from_registry:
        warnings.append(
            f"Team numbers in the grid have no entry in the team registry: "
            f"{sorted(missing_from_registry)}"
        )

    # Replace any previous draw for this division so re-imports (e.g. a corrected
    # draw) start clean rather than accumulating stale fixtures.
    conn.execute("DELETE FROM rounds WHERE division = ?", (division,))

    team_id_by_number: dict[int, int] = {}
    for team_number, info in teams.items():
        conn.execute(
            """
            INSERT INTO teams (division, team_number, name, team_size)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (division, team_number)
            DO UPDATE SET name = excluded.name, team_size = excluded.team_size
            """,
            (division, team_number, info.name, info.team_size),
        )
        # Always look the id up explicitly rather than trusting lastrowid, which is
        # unreliable across the insert vs. upsert-update paths.
        team_id = conn.execute(
            "SELECT id FROM teams WHERE division = ? AND team_number = ?",
            (division, team_number),
        ).fetchone()["id"]
        team_id_by_number[team_number] = team_id

    player_team_ids = set(team_id_by_number.values())
    if players:
        conn.execute(
            "DELETE FROM players WHERE team_id IN ({})".format(
                ",".join("?" for _ in player_team_ids)
            ),
            tuple(player_team_ids),
        )
        positions_by_team: dict[int, set[int]] = {}
        for player in players:
            if player.team_number not in team_id_by_number:
                warnings.append(
                    f"Player {player.name!r} references unknown team number "
                    f"{player.team_number}"
                )
                continue
            team_id = team_id_by_number[player.team_number]
            team_size = teams[player.team_number].team_size
            if not 1 <= player.play_position <= team_size:
                warnings.append(
                    f"{player.name!r} on team {player.team_number} has play position "
                    f"{player.play_position}; expected 1-{team_size}"
                )
                continue
            positions = positions_by_team.setdefault(team_id, set())
            if player.play_position in positions:
                warnings.append(
                    f"Team {player.team_number} has duplicate player position "
                    f"{player.play_position}"
                )
                continue
            positions.add(player.play_position)
            conn.execute(
                "INSERT INTO players (team_id, play_position, name) VALUES (?, ?, ?)",
                (team_id, player.play_position, player.name),
            )
        for team_number, info in teams.items():
            if team_number in team_numbers_in_grid:
                actual = len(positions_by_team.get(team_id_by_number[team_number], set()))
                if actual != info.team_size:
                    warnings.append(
                        f"Team {team_number} roster has {actual} players, "
                        f"expected {info.team_size}"
                    )

    for round_number, row in enumerate(rows, start=1):
        round_id = conn.execute(
            "INSERT INTO rounds (division, round_number) VALUES (?, ?)",
            (division, round_number),
        ).lastrowid
        for i in range(0, len(row) - 1, 2):
            team_a_number, team_b_number = row[i], row[i + 1]
            if team_a_number not in team_id_by_number or team_b_number not in team_id_by_number:
                continue  # already reported via missing_from_registry
            conn.execute(
                """
                INSERT INTO fixtures (round_id, team_a_id, team_b_id, lane_a, lane_b)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    round_id,
                    team_id_by_number[team_a_number],
                    team_id_by_number[team_b_number],
                    i + 1,
                    i + 2,
                ),
            )
    conn.commit()
    return warnings
