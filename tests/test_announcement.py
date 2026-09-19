from counties26 import db
from counties26.announcement import announcement_order, format_announcement


def _add_team(conn, division, number, name, points, players):
    team_id = conn.execute(
        "INSERT INTO teams (division, team_number, name, team_size) VALUES (?, ?, ?, ?)",
        (division, number, name, len(players)),
    ).lastrowid
    fixture_id = conn.execute(
        "INSERT INTO fixtures (round_id, team_a_id, team_b_id, lane_a, lane_b) "
        "VALUES (?, ?, ?, ?, ?)",
        (1, team_id, team_id, number * 2 - 1, number * 2),
    ).lastrowid
    conn.execute(
        "INSERT INTO match_points "
        "(fixture_id, team_id, pinfall_total, bonus_points, team_bonus, total_points) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (fixture_id, team_id, int(points), 0, 0, points),
    )
    for position, player in enumerate(players, start=1):
        conn.execute(
            "INSERT INTO players (team_id, play_position, name) VALUES (?, ?, ?)",
            (team_id, position, player),
        )


def test_announcement_order_and_adjacent_deltas():
    conn = db.connect(":memory:")
    db.init_db(conn)
    conn.execute("INSERT INTO rounds (id, division, round_number) VALUES (1, 'men', 1)")
    for division, scores in (("women", {3: 700, 2: 800, 1: 1000}), ("men", {3: 650, 2: 750, 1: 900})):
        for place, points in scores.items():
            _add_team(conn, division, place, f"{division.title()} {place}", points, [f"{division} player"])
    conn.commit()

    ordered = announcement_order(conn)
    assert [(team.division, team.place) for team in ordered] == [
        ("women", 3),
        ("men", 3),
        ("women", 2),
        ("men", 2),
        ("women", 1),
        ("men", 1),
    ]
    assert ordered[0].points_ahead_of_below is None
    assert ordered[0].points_behind_above == 100
    assert ordered[2].points_behind_above == 200
    assert ordered[2].points_ahead_of_below == 100
    assert ordered[4].points_behind_above is None
    assert ordered[4].points_ahead_of_below == 200

    output = format_announcement(conn)
    assert "3rd place women" in output
    assert "Women 3 — 700 points" in output
    assert "200 ahead of the team below" in output
    assert output.index("3rd place women") < output.index("1st place men")
