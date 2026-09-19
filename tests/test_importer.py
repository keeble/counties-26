import sqlite3

from counties26 import db
from counties26.draw_import import import_draw
from counties26.importer import build_import_report, commit_import


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
