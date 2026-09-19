"""SQLite schema and connection helpers.

All derived data (match points, standings, bowler stats) is recomputed from
``bowler_scores`` and ``fixtures`` rather than hand-maintained, so re-imports and
corrections are always safe.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY,
    division TEXT NOT NULL CHECK (division IN ('men', 'women')),
    team_number INTEGER NOT NULL,
    name TEXT NOT NULL,
    team_size INTEGER NOT NULL,
    UNIQUE (division, team_number)
);

CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY,
    team_id INTEGER NOT NULL REFERENCES teams (id) ON DELETE CASCADE,
    play_position INTEGER NOT NULL,
    name TEXT NOT NULL,
    UNIQUE (team_id, play_position),
    UNIQUE (team_id, name)
);

CREATE TABLE IF NOT EXISTS player_aliases (
    id INTEGER PRIMARY KEY,
    player_id INTEGER NOT NULL REFERENCES players (id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    alias_normalized TEXT NOT NULL,
    UNIQUE (player_id, alias_normalized)
);

CREATE TABLE IF NOT EXISTS rounds (
    id INTEGER PRIMARY KEY,
    division TEXT NOT NULL CHECK (division IN ('men', 'women')),
    round_number INTEGER NOT NULL,
    UNIQUE (division, round_number)
);

CREATE TABLE IF NOT EXISTS fixtures (
    id INTEGER PRIMARY KEY,
    round_id INTEGER NOT NULL REFERENCES rounds (id) ON DELETE CASCADE,
    team_a_id INTEGER NOT NULL REFERENCES teams (id),
    team_b_id INTEGER NOT NULL REFERENCES teams (id),
    lane_a INTEGER NOT NULL,
    lane_b INTEGER NOT NULL,
    UNIQUE (round_id, team_a_id),
    UNIQUE (round_id, team_b_id)
);

CREATE TABLE IF NOT EXISTS bowler_scores (
    id INTEGER PRIMARY KEY,
    fixture_id INTEGER NOT NULL REFERENCES fixtures (id) ON DELETE CASCADE,
    team_id INTEGER NOT NULL REFERENCES teams (id),
    lane INTEGER,
    play_position INTEGER NOT NULL,
    bowler_name TEXT NOT NULL,
    scratch_score INTEGER NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT,
    source_file TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    UNIQUE (team_id, bowler_name, start_date)
);

CREATE TABLE IF NOT EXISTS match_points (
    id INTEGER PRIMARY KEY,
    fixture_id INTEGER NOT NULL REFERENCES fixtures (id) ON DELETE CASCADE,
    team_id INTEGER NOT NULL REFERENCES teams (id),
    pinfall_total INTEGER NOT NULL,
    bonus_points REAL NOT NULL,
    team_bonus REAL NOT NULL,
    total_points REAL NOT NULL,
    UNIQUE (fixture_id, team_id)
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a connection with foreign keys enabled and row access by column name."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create all tables if they don't already exist."""
    conn.executescript(SCHEMA_SQL)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(bowler_scores)")}
    if "lane" not in columns:
        conn.execute("ALTER TABLE bowler_scores ADD COLUMN lane INTEGER")
    conn.commit()
