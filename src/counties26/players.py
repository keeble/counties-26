"""Player identity and alias helpers."""

from __future__ import annotations

import re
import sqlite3

from counties26.constants import require_division


def normalize_player_name(name: str) -> str:
    """Normalize centre-export names for exact alias matching."""
    return re.sub(r"[^a-z0-9]", "", name.casefold())


def add_player_alias(
    conn: sqlite3.Connection,
    division: str,
    team_number: int,
    player_name: str,
    alias: str,
) -> None:
    """Attach a centre-export name to a registered player."""
    require_division(division)
    alias = alias.strip()
    player_name = player_name.strip()
    if not alias or not player_name:
        raise ValueError("Player name and alias must not be empty")

    team = conn.execute(
        """
        SELECT id
        FROM teams
        WHERE division = ? AND team_number = ?
        """,
        (division, team_number),
    ).fetchone()
    if team is None:
        raise ValueError(
            f"No registered team {team_number} found in {division} division"
        )

    canonical_name = resolve_player_name(conn, team["id"], player_name)
    if canonical_name is None:
        raise ValueError(
            f"Could not uniquely resolve player {player_name!r} on "
            f"{division} team {team_number}; use the full registered name"
        )
    player = conn.execute(
        "SELECT id FROM players WHERE team_id = ? AND name = ?",
        (team["id"], canonical_name),
    ).fetchone()

    normalized = normalize_player_name(alias)
    if not normalized:
        raise ValueError("Alias must contain at least one letter or number")
    conn.execute(
        """
        INSERT INTO player_aliases (player_id, alias, alias_normalized)
        VALUES (?, ?, ?)
        ON CONFLICT (player_id, alias_normalized)
        DO UPDATE SET alias = excluded.alias
        """,
        (player["id"], alias, normalized),
    )
    conn.commit()


def resolve_player_name(
    conn: sqlite3.Connection, team_id: int, export_name: str
) -> str | None:
    """Return the canonical roster name for a centre-export name or alias.

    Matching is deliberately scoped to one team. Ambiguous aliases return None
    so an import never silently assigns a score to the wrong player.
    """
    normalized = normalize_player_name(export_name)
    if not normalized:
        return None
    players = conn.execute(
        "SELECT id, name FROM players WHERE team_id = ?",
        (team_id,),
    ).fetchall()
    matches = [
        player["name"]
        for player in players
        if normalize_player_name(player["name"]) == normalized
    ]
    aliases = conn.execute(
        """
        SELECT p.name
        FROM player_aliases pa
        JOIN players p ON p.id = pa.player_id
        WHERE p.team_id = ? AND pa.alias_normalized = ?
        """,
        (team_id, normalized),
    ).fetchall()
    matches.extend(row["name"] for row in aliases)
    unique_matches = sorted(set(matches))
    if len(unique_matches) == 1:
        return unique_matches[0]
    if unique_matches:
        return None

    export_parts = export_name.casefold().split()
    if not export_parts:
        return None

    def name_parts(name: str) -> list[str]:
        return re.findall(r"[a-z0-9]+", name.casefold())

    candidates = [player["name"] for player in players]
    first_name_matches = [
        name
        for name in candidates
        if name_parts(name) and name_parts(name)[0] == export_parts[0]
    ]
    if len(first_name_matches) == 1 and len(export_parts) == 1:
        return first_name_matches[0]

    if len(export_parts) >= 2:
        initial_matches = [
            name
            for name in candidates
            if len(name_parts(name)) >= 2
            and name_parts(name)[0] == export_parts[0]
            and name_parts(name)[1].startswith(export_parts[1][0])
        ]
        if len(initial_matches) == 1:
            return initial_matches[0]

    surname_matches = [
        name
        for name in candidates
        if name_parts(name) and name_parts(name)[-1] == export_parts[-1]
    ]
    if len(surname_matches) == 1:
        return surname_matches[0]
    return None