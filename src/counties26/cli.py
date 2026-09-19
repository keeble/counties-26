"""Typer CLI for the counties26 scoring tool."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

import typer

from counties26 import db
from counties26.announcement import format_announcement
from counties26.draw_import import import_draw
from counties26.importer import build_import_report, commit_import, write_unknown_aliases
from counties26.players import add_player_alias
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
    players_csv: Optional[Path] = typer.Option(
        None, "--players", help="Optional starting roster CSV"
    ),
    first_lane: int = typer.Option(
        1, "--first-lane", help="Physical centre lane represented by grid column 1"
    ),
    db_path: Path = DB_OPTION,
) -> None:
    """Import the lane draw (grid + team registry) for one division."""
    conn = _connect(db_path)
    warnings = import_draw(conn, grid_csv, teams_csv, division, players_csv, first_lane)
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
    swap_lanes: bool = typer.Option(
        False,
        "--swap-lanes",
        help="Assign the first physical lane to the second draw team, and vice versa",
    ),
    division: str = typer.Option(..., help="'men' or 'women'"),
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt"),
    unknown_aliases: Optional[Path] = typer.Option(
        None,
        "--unknown-aliases",
        help="Write unresolved player names to an editable CSV",
    ),
    db_path: Path = DB_OPTION,
) -> None:
    """Import a round of lane-software scores, after showing a validation report."""
    conn = _connect(db_path)
    report = build_import_report(
        conn, csv_path, division, round, block_game=game, swap_lanes=swap_lanes
    )

    if unknown_aliases:
        write_unknown_aliases(unknown_aliases, division, report)
        typer.echo(f"Unknown player names written to {unknown_aliases}")

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


@app.command("add-alias")
def add_alias_cmd(
    alias: str,
    division: str = typer.Option(..., help="'men' or 'women'"),
    team_number: int = typer.Option(..., "--team-number", help="Registered team number"),
    player_name: str = typer.Option(..., "--player", help="Canonical registered player name"),
    db_path: Path = DB_OPTION,
) -> None:
    """Remember a bowling-centre name or abbreviation for a registered player."""
    conn = _connect(db_path)
    try:
        add_player_alias(conn, division, team_number, player_name, alias)
    except ValueError as error:
        typer.secho(str(error), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from error
    typer.secho(
        f"Added alias {alias!r} for {player_name!r} on team {team_number}.",
        fg=typer.colors.GREEN,
    )


@app.command("add-aliases")
def add_aliases_cmd(
    aliases_csv: Path,
    db_path: Path = DB_OPTION,
) -> None:
    """Add aliases from an edited unknown-player CSV."""
    conn = _connect(db_path)
    added = 0
    with open(aliases_csv, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            player_name = row.get("player_name", "").strip()
            if not player_name:
                typer.secho(
                    f"Missing player_name for alias {row.get('alias', '')!r}",
                    fg=typer.colors.RED,
                    err=True,
                )
                raise typer.Exit(code=2)
            try:
                add_player_alias(
                    conn,
                    row["division"].strip(),
                    int(row["team_number"]),
                    player_name,
                    row["alias"].strip(),
                )
            except (KeyError, ValueError) as error:
                typer.secho(str(error), fg=typer.colors.RED, err=True)
                raise typer.Exit(code=2) from error
            added += 1
    typer.secho(f"Added or updated {added} aliases.", fg=typer.colors.GREEN)


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


@app.command("announce-winners")
def announce_winners_cmd(
    db_path: Path = DB_OPTION,
) -> None:
    """Print the PA-ready final-place announcement for women and men."""
    conn = _connect(db_path)
    typer.echo(format_announcement(conn))


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
