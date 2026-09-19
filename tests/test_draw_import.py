import sqlite3

import pytest

from counties26 import db
from counties26.draw_import import import_draw, validate_round_robin

# A verified complete single round robin for 10 teams: 9 rounds, no header row/column,
# column position is the lane number.
COMPLETE_GRID = [
    [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    [7, 3, 1, 6, 2, 9, 5, 10, 8, 4],
    [4, 5, 9, 8, 10, 1, 3, 2, 6, 7],
    [9, 1, 5, 3, 4, 7, 8, 6, 10, 2],
    [10, 7, 6, 2, 8, 3, 4, 1, 5, 9],
    [5, 8, 4, 10, 7, 2, 6, 9, 1, 3],
    [6, 4, 7, 9, 1, 5, 10, 3, 2, 8],
    [3, 9, 8, 1, 6, 10, 2, 4, 7, 5],
    [8, 10, 2, 5, 9, 4, 1, 7, 3, 6],
]


def _write_grid(path, rows):
    path.write_text("\n".join(",".join(str(v) for v in row) for row in rows))


def _write_teams(path, count):
    lines = ["team_number,team_name"]
    lines += [f"{i},Team {i}" for i in range(1, count + 1)]
    path.write_text("\n".join(lines))


def test_validate_round_robin_accepts_the_complete_example():
    assert validate_round_robin(COMPLETE_GRID) == []


def test_validate_round_robin_flags_a_missing_round():
    assert validate_round_robin(COMPLETE_GRID[:-1]) != []


def test_validate_round_robin_flags_a_repeated_pairing():
    broken = [row[:] for row in COMPLETE_GRID]
    broken[-1] = broken[0]  # duplicates round 1's pairings
    warnings = validate_round_robin(broken)
    assert any("meet more than once" in w for w in warnings)


def test_import_draw_builds_expected_fixtures(tmp_path):
    grid_path = tmp_path / "grid.csv"
    teams_path = tmp_path / "teams.csv"
    _write_grid(grid_path, COMPLETE_GRID)
    _write_teams(teams_path, 10)

    conn = db.connect(":memory:")
    db.init_db(conn)

    warnings = import_draw(conn, grid_path, teams_path, "men")
    assert warnings == []

    rounds = conn.execute("SELECT COUNT(*) AS n FROM rounds WHERE division = 'men'").fetchone()
    assert rounds["n"] == 9

    fixtures = conn.execute("SELECT COUNT(*) AS n FROM fixtures").fetchone()
    assert fixtures["n"] == 9 * 5

    round1 = conn.execute(
        "SELECT id FROM rounds WHERE division = 'men' AND round_number = 1"
    ).fetchone()
    fixture = conn.execute(
        """
        SELECT ta.name AS a, tb.name AS b, f.lane_a, f.lane_b
        FROM fixtures f
        JOIN teams ta ON ta.id = f.team_a_id
        JOIN teams tb ON tb.id = f.team_b_id
        WHERE f.round_id = ? AND f.lane_a = 1
        """,
        (round1["id"],),
    ).fetchone()
    assert (fixture["a"], fixture["b"]) == ("Team 1", "Team 2")
    assert (fixture["lane_a"], fixture["lane_b"]) == (1, 2)
