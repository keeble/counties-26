from counties26 import db
from counties26.site.data import division_page_data, team_slug


def test_same_county_name_has_distinct_division_team_urls():
    assert team_slug(1, "men", "Surrey") != team_slug(1, "women", "Surrey")


def test_division_team_links_are_scoped_to_their_division():
    conn = db.connect(":memory:")
    db.init_db(conn)
    for division in ("men", "women"):
        conn.execute(
            "INSERT INTO teams (division, team_number, name, team_size) "
            "VALUES (?, 1, 'Surrey', 4)",
            (division,),
        )
    conn.commit()

    men_id = conn.execute("SELECT id FROM teams WHERE division = 'men'").fetchone()[0]
    women_id = conn.execute("SELECT id FROM teams WHERE division = 'women'").fetchone()[0]
    men_links = division_page_data(conn, "men")["team_links"]
    women_links = division_page_data(conn, "women")["team_links"]

    assert men_links[men_id]["href"] != women_links[women_id]["href"]