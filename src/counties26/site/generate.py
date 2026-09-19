"""Static site builder — renders standings/bowler stats for gh-pages publishing."""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from counties26.standings import bowler_stats, team_standings

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

DIVISION_TITLES = {"men": "Men's", "women": "Women's"}


def build_site(conn: sqlite3.Connection, output_dir: str | Path) -> None:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    index_template = env.get_template("index.html")
    (output_path / "index.html").write_text(index_template.render(generated_at=generated_at))

    division_template = env.get_template("division.html")
    for division, title in DIVISION_TITLES.items():
        html = division_template.render(
            division_title=title,
            standings=team_standings(conn, division),
            bowlers=bowler_stats(conn, division),
            generated_at=generated_at,
        )
        (output_path / f"{division}.html").write_text(html)

    shutil.copy(STATIC_DIR / "style.css", output_path / "style.css")
