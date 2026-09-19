import sqlite3

from counties26 import db
from counties26.draw_import import import_draw
from counties26.importer import (
    build_import_report,
    commit_import,
    parse_score_csv,
    write_unknown_aliases,
)


def _setup_draw(tmp_path, conn, division, team_numbers):
    """A minimal round robin: N teams on lanes 1..N, using the standard team size
    for the division (5 for men, 4 for women)."""
    grid_path = tmp_path / f"{division}_grid.csv"
    teams_path = tmp_path / f"{division}_teams.csv"
    grid_path.write_text(",".join(str(n) for n in team_numbers))
    lines = ["team_number,team_name"] + [f"{n},Team {n}" for n in team_numbers]
    teams_path.write_text("\n".join(lines))
    return import_draw(conn, grid_path, teams_path, division)


def _score_csv_rows(team_lane, team_name, scores, start_date="2026-06-01 10:00"):
    rows = []
    for position, score in enumerate(scores, start=1):
        rows.append(
            {
                "Lane number": str(team_lane),
                "Team name": team_name,
                "Bowler name": f"{team_name} P{position}",
                "Play position": str(position),
                "Scratch": str(score),
                "Start date": start_date,
                "End date": "2026-06-01 10:30",
            }
        )
    return rows


def _write_csv(path, rows):
    header = ["Lane number", "Team name", "Bowler name", "Play position", "Scratch", "Start date", "End date"]
    lines = [",".join(header)]
    for row in rows:
        lines.append(",".join(row[col] for col in header))
    path.write_text("\n".join(lines))


def test_import_new_round_computes_match_points(tmp_path):
    conn = db.connect(":memory:")
    db.init_db(conn)
    _setup_draw(tmp_path, conn, "men", [1, 2])  # 1 round, lanes 1 & 2

    rows = _score_csv_rows(1, "Team 1", [200] * 5) + _score_csv_rows(2, "Team 2", [190] * 5)
    csv_path = tmp_path / "round1.csv"
    _write_csv(csv_path, rows)

    report = build_import_report(conn, csv_path, "men", 1)
    assert report.rows_new == 10
    assert report.warnings == []

    notes = commit_import(conn, csv_path, report)
    assert notes == []

    points = conn.execute(
        "SELECT t.name, mp.total_points FROM match_points mp JOIN teams t ON t.id = mp.team_id ORDER BY t.name"
    ).fetchall()
    assert dict((r["name"], r["total_points"]) for r in points) == {
        "Team 1": 1100.0,
        "Team 2": 950.0,
    }


def test_original_export_columns_and_block_game_filter(tmp_path):
    conn = db.connect(":memory:")
    db.init_db(conn)
    _setup_draw(tmp_path, conn, "men", [1, 2])

    csv_path = tmp_path / "centre-export.csv"
    csv_path.write_text(
        "Open mode,Game number,Lane number,Bowler name,Play position,Scratch,Team name,Start date,End date\n"
        "Open pair,1,1,A,1,200,Team 1,2026-06-01 10:00,2026-06-01 10:30\n"
        "Open pair,1,2,B,1,190,Team 2,2026-06-01 10:00,2026-06-01 10:30\n"
        "Open pair,2,1,A,1,180,Team 1,2026-06-01 11:00,2026-06-01 11:30\n"
        "Open pair,2,2,B,1,170,Team 2,2026-06-01 11:00,2026-06-01 11:30\n"
    )

    rows = parse_score_csv(csv_path)
    assert len(rows) == 4
    assert rows[0].game_number == 1

    report = build_import_report(conn, csv_path, "men", 1, block_game=1)
    assert report.rows_in_file == 4
    assert report.rows_other_game == 2
    assert report.rows_new == 2


def test_known_player_alias_resolves_to_canonical_roster_name(tmp_path):
    conn = db.connect(":memory:")
    db.init_db(conn)
    grid_path = tmp_path / "grid.csv"
    teams_path = tmp_path / "teams.csv"
    players_path = tmp_path / "players.csv"
    grid_path.write_text("1,2")
    teams_path.write_text("team_number,team_name,team_size\n1,Team 1,5\n2,Team 2,5\n")
    players_path.write_text(
        "team_number,play_position,player_name\n"
        "1,1,Laura Morgan\n1,2,Bob Example\n1,3,Cara Example\n1,4,Dan Example\n1,5,Eve Example\n"
        "2,1,A\n2,2,B\n2,3,C\n2,4,D\n2,5,E\n"
    )
    import_draw(conn, grid_path, teams_path, "men", players_path)
    from counties26.players import add_player_alias

    add_player_alias(conn, "men", 1, "Laura Morgan", "Laura M")
    rows = _score_csv_rows(1, "Team 1", [200] * 5)
    rows[0]["Bowler name"] = "Laura M"
    rows[1]["Bowler name"] = "Bob Example"
    rows[2]["Bowler name"] = "Cara Example"
    rows[3]["Bowler name"] = "Dan Example"
    rows[4]["Bowler name"] = "Eve Example"
    rows += _score_csv_rows(2, "Team 2", [190] * 5)
    for row, name in zip(rows[5:], ["A", "B", "C", "D", "E"]):
        row["Bowler name"] = name
    csv_path = tmp_path / "round1.csv"
    _write_csv(csv_path, rows)

    report = build_import_report(conn, csv_path, "men", 1)
    assert report.rows_new == 10
    assert report.rows_player_mismatch == 0
    commit_import(conn, csv_path, report)
    saved = conn.execute(
        "SELECT bowler_name FROM bowler_scores WHERE team_id = "
        "(SELECT id FROM teams WHERE team_number = 1) ORDER BY play_position"
    ).fetchall()
    assert saved[0]["bowler_name"] == "Laura Morgan"


def test_unknown_player_name_is_flagged_when_roster_exists(tmp_path):
    conn = db.connect(":memory:")
    db.init_db(conn)
    _setup_draw(tmp_path, conn, "men", [1, 2])
    conn.execute(
        "INSERT INTO players (team_id, play_position, name) "
        "SELECT id, 1, 'Unknown' FROM teams WHERE team_number = 1"
    )
    for position, name in enumerate(["Known 2", "Known 3", "Known 4", "Known 5"], start=2):
        conn.execute(
            "INSERT INTO players (team_id, play_position, name) "
            "SELECT id, ?, ? FROM teams WHERE team_number = 1",
            (position, name),
        )
    conn.commit()
    rows = _score_csv_rows(1, "Team 1", [200] * 5) + _score_csv_rows(2, "Team 2", [190] * 5)
    rows[0]["Bowler name"] = "Not Registered"
    for row, name in zip(rows[1:5], ["Known 2", "Known 3", "Known 4", "Known 5"]):
        row["Bowler name"] = name
    csv_path = tmp_path / "round1.csv"
    _write_csv(csv_path, rows)

    report = build_import_report(conn, csv_path, "men", 1)
    assert report.rows_player_mismatch == 1
    assert report.rows_new == 9


def test_unknown_aliases_can_be_written_for_later_batch_import(tmp_path):
    conn = db.connect(":memory:")
    db.init_db(conn)
    _setup_draw(tmp_path, conn, "men", [1, 2])
    conn.execute(
        "INSERT INTO players (team_id, play_position, name) "
        "SELECT id, 1, 'Known' FROM teams WHERE team_number = 1"
    )
    conn.commit()
    rows = _score_csv_rows(1, "Team 1", [200] * 5) + _score_csv_rows(2, "Team 2", [190] * 5)
    for row in rows[:5]:
        row["Bowler name"] = "Gaz"
    csv_path = tmp_path / "round1.csv"
    output_path = tmp_path / "unknown.csv"
    _write_csv(csv_path, rows)

    report = build_import_report(conn, csv_path, "men", 1)
    write_unknown_aliases(output_path, "men", report)

    assert output_path.read_text().splitlines() == [
        "division,team_number,team_name,alias,player_name",
        "men,1,Team 1,Gaz,",
    ]


def test_multiple_block_games_require_selection(tmp_path):
    conn = db.connect(":memory:")
    db.init_db(conn)
    _setup_draw(tmp_path, conn, "men", [1, 2])

    rows = _score_csv_rows(1, "Team 1", [200] * 5) + _score_csv_rows(2, "Team 2", [190] * 5)
    csv_path = tmp_path / "cumulative.csv"
    header = "Game number,Lane number,Team name,Bowler name,Play position,Scratch,Start date,End date\n"
    game_rows = []
    for game_number, start_date in ((1, "2026-06-01 10:00"), (2, "2026-06-01 11:00")):
        for row in rows:
            game_rows.append(
                f"{game_number},{row['Lane number']},{row['Team name']},{row['Bowler name']},"
                f"{row['Play position']},{row['Scratch']},{start_date},{row['End date']}"
            )
    csv_path.write_text(header + "\n".join(game_rows))

    report = build_import_report(conn, csv_path, "men", 1)
    assert report.rows_new == 0
    assert any("specify --game" in warning for warning in report.warnings)


def test_reimport_same_file_is_idempotent(tmp_path):
    conn = db.connect(":memory:")
    db.init_db(conn)
    _setup_draw(tmp_path, conn, "men", [1, 2])

    rows = _score_csv_rows(1, "Team 1", [200] * 5) + _score_csv_rows(2, "Team 2", [190] * 5)
    csv_path = tmp_path / "round1.csv"
    _write_csv(csv_path, rows)

    report1 = build_import_report(conn, csv_path, "men", 1)
    commit_import(conn, csv_path, report1)

    report2 = build_import_report(conn, csv_path, "men", 1)
    assert report2.rows_new == 0
    assert report2.rows_duplicate == 10

    total_rows = conn.execute("SELECT COUNT(*) AS n FROM bowler_scores").fetchone()["n"]
    assert total_rows == 10


def test_other_division_lanes_are_ignored(tmp_path):
    conn = db.connect(":memory:")
    db.init_db(conn)
    _setup_draw(tmp_path, conn, "men", [1, 2])  # men's fixtures only use lanes 1 & 2

    # Lane 99 stands in for a lane used by the concurrently-running other division;
    # it isn't part of any men's fixture, so its rows must be ignored outright.
    rows = _score_csv_rows(1, "Team 1", [200] * 5) + _score_csv_rows(2, "Team 2", [190] * 5)
    rows += _score_csv_rows(99, "Team 1", [150] * 4)
    csv_path = tmp_path / "combined.csv"
    _write_csv(csv_path, rows)

    report = build_import_report(conn, csv_path, "men", 1)
    assert report.rows_new == 10
    assert report.rows_other_division == 4


def test_team_name_mismatch_is_flagged(tmp_path):
    conn = db.connect(":memory:")
    db.init_db(conn)
    _setup_draw(tmp_path, conn, "men", [1, 2])

    rows = _score_csv_rows(1, "Wrong Team Name", [200] * 5) + _score_csv_rows(2, "Team 2", [190] * 5)
    csv_path = tmp_path / "round1.csv"
    _write_csv(csv_path, rows)

    report = build_import_report(conn, csv_path, "men", 1)
    assert report.rows_team_mismatch == 5
    assert any("expected team" in w for w in report.warnings)


def test_missing_game_is_flagged(tmp_path):
    conn = db.connect(":memory:")
    db.init_db(conn)
    _setup_draw(tmp_path, conn, "men", [1, 2])

    rows = _score_csv_rows(1, "Team 1", [200] * 5)  # team 2 never bowled
    csv_path = tmp_path / "round1.csv"
    _write_csv(csv_path, rows)

    report = build_import_report(conn, csv_path, "men", 1)
    assert any("no rows found in this export" in w for w in report.warnings)


def test_wrong_player_count_is_flagged(tmp_path):
    conn = db.connect(":memory:")
    db.init_db(conn)
    _setup_draw(tmp_path, conn, "men", [1, 2])

    rows = _score_csv_rows(1, "Team 1", [200] * 4) + _score_csv_rows(2, "Team 2", [190] * 5)
    csv_path = tmp_path / "round1.csv"
    _write_csv(csv_path, rows)

    report = build_import_report(conn, csv_path, "men", 1)
    assert any("expected 5" in w for w in report.warnings)
