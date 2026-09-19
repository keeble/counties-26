from counties26 import db
from counties26.players import add_player_alias, resolve_player_name


def _connection_with_roster():
    conn = db.connect(":memory:")
    db.init_db(conn)
    conn.execute(
        "INSERT INTO teams (division, team_number, name, team_size) "
        "VALUES ('men', 1, 'Team 1', 5)"
    )
    team_id = conn.execute("SELECT id FROM teams").fetchone()["id"]
    names = ["Gareth Jones", "Laura Morgan", "Laura Smith", "Ben Carter"]
    for position, name in enumerate(names, start=1):
        conn.execute(
            "INSERT INTO players (team_id, play_position, name) VALUES (?, ?, ?)",
            (team_id, position, name),
        )
    conn.commit()
    return conn, team_id


def test_player_name_fallbacks_are_team_scoped_and_unambiguous():
    conn, team_id = _connection_with_roster()
    add_player_alias(conn, "men", 1, "Gareth Jones", "Gaz")

    assert resolve_player_name(conn, team_id, "Gaz") == "Gareth Jones"
    assert resolve_player_name(conn, team_id, "Gareth") == "Gareth Jones"
    assert resolve_player_name(conn, team_id, "Gareth J") == "Gareth Jones"
    assert resolve_player_name(conn, team_id, "Jones") == "Gareth Jones"
    assert resolve_player_name(conn, team_id, "Laura") is None


def test_player_name_fallbacks_match_unique_first_initial():
    conn, team_id = _connection_with_roster()
    assert resolve_player_name(conn, team_id, "Ben C") == "Ben Carter"


def test_player_name_alias_and_canonical_match_take_priority():
    conn, team_id = _connection_with_roster()
    add_player_alias(conn, "men", 1, "Gareth Jones", "GJ")
    assert resolve_player_name(conn, team_id, "GJ") == "Gareth Jones"
    assert resolve_player_name(conn, team_id, "Gareth Jones") == "Gareth Jones"
