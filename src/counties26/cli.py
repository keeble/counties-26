"""Typer CLI for the counties26 scoring tool."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from counties26 import db
from counties26.draw_import import import_draw
from counties26.importer import build_import_report, commit_import
from counties26.site.generate import build_site as _build_site
from counties26.standings import bowler_stats, team_standings

app = typer.Typer(help="Scoring tool for the County Championships 2026 bowling tournament")

DB_OPTION = typer.Option("counties26.db", "--db", help="Path to the SQLite database file")


def _connect(db_path: Path):
    conn = db.connect(db_path)
    db.init_db(conn)
    return conn


@app.command("import-draw")
def import_draw_cmd(
    grid_csv: Path,
    teams_csv: Path,
    division: str = typer.Option(..., help="'men' or 'women'"),
    db_path: Path = DB_OPTION,
) -> None:
    """Import the lane draw (grid + team registry) for one division."""
    conn = _connect(db_path)
    warnings = import_draw(conn, grid_csv, teams_csv, division)
    if warnings:
        typer.secho("Warnings:", fg=typer.colors.YELLOW, bold=True)
        for warning in warnings:
            typer.echo(f"  - {warning}")
    typer.secho(f"Draw imported for {division}.", fg=typer.colors.GREEN)


@app.command("import")
def import_cmd(
    csv_path: Path,
    round: int = typer.Option(
        ..., "--round", "--tournament-game", help="Tournament game/round number"
    ),
    game: int = typer.Option(
        ..., "--game", help="Game number within the centre's exported game block"
    ),
    division: str = typer.Option(..., help="'men' or 'women'"),
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt"),
    db_path: Path = DB_OPTION,
) -> None:
    """Import a round of lane-software scores, after showing a validation report."""
    conn = _connect(db_path)
    report = build_import_report(conn, csv_path, division, round, block_game=game)

    typer.echo(report.summary())
    if report.rows_new == 0:
        typer.secho("Nothing new to import.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=0)

    if not yes and not typer.confirm("Proceed with this import?"):
        typer.secho("Aborted — nothing was written.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    notes = commit_import(conn, csv_path, report)
    typer.secho(f"Imported {report.rows_new} new bowler scores.", fg=typer.colors.GREEN)
    for note in notes:
        typer.secho(f"  - {note}", fg=typer.colors.YELLOW)


@app.command("show-standings")
def show_standings_cmd(
    division: str = typer.Option(..., help="'men' or 'women'"),
    db_path: Path = DB_OPTION,
) -> None:
    """Print current team standings and bowler averages for one division."""
    conn = _connect(db_path)
    typer.secho(f"{division.title()} team standings", bold=True)
    for team in team_standings(conn, division):
        typer.echo(
            f"  {team.team_name:<24} played={team.played:<3} "
            f"points={team.total_points:<7} pinfall={team.total_pinfall}"
        )

    typer.secho(f"\n{division.title()} bowler averages", bold=True)
    for bowler in bowler_stats(conn, division):
        typer.echo(
            f"  {bowler.bowler_name:<20} {bowler.team_name:<24} "
            f"games={bowler.games_played:<3} avg={bowler.average:<6} high={bowler.high_score}"
        )


@app.command("build-site")
def build_site_cmd(
    output: Path = typer.Option("docs", "--output", help="Output directory for the static site"),
    db_path: Path = DB_OPTION,
) -> None:
    """Render the static standings site for publishing to GitHub Pages."""
    conn = _connect(db_path)
    _build_site(conn, output)
    typer.secho(f"Site built at {output}", fg=typer.colors.GREEN)


if __name__ == "__main__":
    app()
