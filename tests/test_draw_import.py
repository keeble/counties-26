import sqlite3

import pytest

from counties26 import db
from counties26.draw_import import import_draw, parse_player_registry, validate_round_robin
from counties26.players import add_player_alias

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


def test_parse_grid_accepts_utf8_bom(tmp_path):
    grid_path = tmp_path / "bom-grid.csv"
    grid_path.write_text("6,7\n8,9\n", encoding="utf-8-sig")

    from counties26.draw_import import parse_grid

    assert parse_grid(grid_path) == [[6, 7], [8, 9]]


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


def test_import_draw_maps_grid_columns_to_physical_first_lane(tmp_path):
    grid_path = tmp_path / "grid.csv"
    teams_path = tmp_path / "teams.csv"
    _write_grid(grid_path, [[1, 2]])
    _write_teams(teams_path, 2)

    conn = db.connect(":memory:")
    db.init_db(conn)
    import_draw(conn, grid_path, teams_path, "men", first_lane=11)

    lanes = conn.execute("SELECT lane_a, lane_b FROM fixtures").fetchone()
    assert (lanes["lane_a"], lanes["lane_b"]) == (11, 12)


def test_import_draw_loads_starting_player_roster(tmp_path):
    grid_path = tmp_path / "grid.csv"
    teams_path = tmp_path / "teams.csv"
    players_path = tmp_path / "players.csv"
    _write_grid(grid_path, [[1, 2]])
    _write_teams(teams_path, 2)
    players_path.write_text(
        "team_number,player_name\n"
        "1,Alice Example\n1,Bob Example\n1,Erin Example\n"
        "2,Carol Example\n2,Dan Example\n"
    )

    conn = db.connect(":memory:")
    db.init_db(conn)
    warnings = import_draw(conn, grid_path, teams_path, "men", players_path)

    assert warnings == []
    assert len(parse_player_registry(players_path)) == 5
    players = conn.execute(
        "SELECT p.name FROM players p JOIN teams t ON t.id = p.team_id "
        "WHERE t.team_number = 1 ORDER BY p.play_position"
    ).fetchall()
    assert [row["name"] for row in players] == [
        "Alice Example",
        "Bob Example",
        "Erin Example",
    ]


def test_add_player_alias_is_normalized_and_idempotent(tmp_path):
    grid_path = tmp_path / "grid.csv"
    teams_path = tmp_path / "teams.csv"
    players_path = tmp_path / "players.csv"
    _write_grid(grid_path, [[1, 2]])
    _write_teams(teams_path, 2)
    players_path.write_text(
        "team_number,player_name\n"
        "1,Alice Example\n1,Bob Example\n"
        "2,Carol Example\n2,Dan Example\n"
    )

    conn = db.connect(":memory:")
    db.init_db(conn)
    import_draw(conn, grid_path, teams_path, "men", players_path)

    add_player_alias(conn, "men", 1, "Alice Example", "A. Example")
    add_player_alias(conn, "men", 1, "Alice Example", "a example")
    aliases = conn.execute(
        "SELECT alias, alias_normalized FROM player_aliases ORDER BY alias"
    ).fetchall()
    assert [(row["alias"], row["alias_normalized"]) for row in aliases] == [
        ("a example", "aexample"),
    ]
