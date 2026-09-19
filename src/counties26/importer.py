"""Import a lane-software score export for a single round.

Handles three sources of real-world messiness, in order:
1. Men's and women's games run concurrently and may be exported in one combined
   file — rows on lanes outside the requested division's fixtures are ignored.
2. The lane software's export appears cumulative across games on a lane, so rows
   already recorded (matched by team + bowler name + start date) are skipped rather
   than double-counted.
3. Nothing is written to the database until a validation report has been shown and
   explicitly confirmed.
"""

from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from counties26.constants import require_division
from counties26.players import resolve_player_name
from counties26.results import recompute_fixture


@dataclass(frozen=True)
class ScoreRow:
    lane: int
    team_name: str
    bowler_name: str
    play_position: int
    scratch: int
    game_number: int | None
    start_date: str
    end_date: str


@dataclass(frozen=True)
class LaneAssignment:
    fixture_id: int
    team_id: int
    team_number: int
    team_name: str
    team_size: int


@dataclass
class ImportReport:
    rows_in_file: int = 0
    rows_other_division: int = 0
    rows_other_game: int = 0
    rows_team_mismatch: int = 0
    rows_player_mismatch: int = 0
    unknown_player_aliases: list[tuple[int, str, str]] = field(default_factory=list)
    rows_duplicate: int = 0
    rows_new: int = 0
    warnings: list[str] = field(default_factory=list)
    # Rows confirmed ready to insert, paired with the lane assignment resolved for them.
    to_insert: list[tuple[LaneAssignment, ScoreRow]] = field(default_factory=list)
    affected_fixture_ids: set[int] = field(default_factory=set)

    def summary(self) -> str:
        lines = [
            f"Rows in file: {self.rows_in_file}",
            f"Ignored (other game in block): {self.rows_other_game}",
            f"Ignored (other division's lanes): {self.rows_other_division}",
            f"Ignored (team name mismatch for that lane): {self.rows_team_mismatch}",
            f"Ignored (unrecognized player name): {self.rows_player_mismatch}",
            f"Already imported (duplicate): {self.rows_duplicate}",
            f"New rows to insert: {self.rows_new}",
        ]
        if self.warnings:
            lines.append("")
            lines.append("Warnings:")
            lines.extend(f"  - {w}" for w in self.warnings)
        return "\n".join(lines)


def parse_score_csv(path: str | Path) -> list[ScoreRow]:
    rows: list[ScoreRow] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            rows.append(
                ScoreRow(
                    lane=int(raw["Lane number"]),
                    team_name=raw["Team name"].strip(),
                    bowler_name=raw["Bowler name"].strip(),
                    play_position=int(raw["Play position"]),
                    scratch=int(raw["Scratch"]),
                    game_number=(
                        int(raw["Game number"])
                        if raw.get("Game number", "").strip()
                        else None
                    ),
                    start_date=raw["Start date"].strip(),
                    end_date=raw["End date"].strip(),
                )
            )
    return rows


def _lane_assignments(
    conn: sqlite3.Connection, division: str, round_number: int
) -> dict[int, LaneAssignment]:
    round_row = conn.execute(
        "SELECT id FROM rounds WHERE division = ? AND round_number = ?",
        (division, round_number),
    ).fetchone()
    if round_row is None:
        raise ValueError(
            f"No round {round_number} found for division {division!r} — import the draw first"
        )
    round_id = round_row["id"]

    fixtures = conn.execute(
        """
        SELECT f.id AS fixture_id, f.lane_a, f.lane_b,
               ta.id AS team_a_id, ta.team_number AS team_a_number,
               ta.name AS team_a_name, ta.team_size AS team_a_size,
               tb.id AS team_b_id, tb.team_number AS team_b_number,
               tb.name AS team_b_name, tb.team_size AS team_b_size
        FROM fixtures f
        JOIN teams ta ON ta.id = f.team_a_id
        JOIN teams tb ON tb.id = f.team_b_id
        WHERE f.round_id = ?
        """,
        (round_id,),
    ).fetchall()

    lanes: dict[int, LaneAssignment] = {}
    for fx in fixtures:
        lanes[fx["lane_a"]] = LaneAssignment(
            fixture_id=fx["fixture_id"],
            team_id=fx["team_a_id"],
            team_number=fx["team_a_number"],
            team_name=fx["team_a_name"],
            team_size=fx["team_a_size"],
        )
        lanes[fx["lane_b"]] = LaneAssignment(
            fixture_id=fx["fixture_id"],
            team_id=fx["team_b_id"],
            team_number=fx["team_b_number"],
            team_name=fx["team_b_name"],
            team_size=fx["team_b_size"],
        )
    return lanes


def _already_imported(conn: sqlite3.Connection, team_id: int, bowler_name: str, start_date: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM bowler_scores WHERE team_id = ? AND bowler_name = ? AND start_date = ?",
        (team_id, bowler_name, start_date),
    ).fetchone()
    return row is not None


def build_import_report(
    conn: sqlite3.Connection,
    csv_path: str | Path,
    division: str,
    round_number: int,
    block_game: int | None = None,
) -> ImportReport:
    require_division(division)
    lanes = _lane_assignments(conn, division, round_number)
    division_lanes = set(lanes)

    rows = parse_score_csv(csv_path)
    report = ImportReport(rows_in_file=len(rows))

    game_numbers = {row.game_number for row in rows if row.game_number is not None}
    if block_game is None and len(game_numbers) > 1:
        report.warnings.append(
            f"This export contains multiple games in the block ({sorted(game_numbers)}); "
            "specify --game to select one before importing"
        )
        return report

    matched_by_team: dict[int, list[ScoreRow]] = {}
    teams_with_data: set[tuple[int, int]] = set()

    for row in rows:
        if block_game is not None and row.game_number is not None and row.game_number != block_game:
            report.rows_other_game += 1
            continue
        if row.lane not in division_lanes:
            report.rows_other_division += 1
            continue
        assignment = lanes[row.lane]
        if row.team_name.strip().lower() != assignment.team_name.strip().lower():
            report.rows_team_mismatch += 1
            report.warnings.append(
                f"Lane {row.lane}: expected team {assignment.team_name!r}, "
                f"CSV says {row.team_name!r} — row ignored"
            )
            continue

        canonical_name = resolve_player_name(conn, assignment.team_id, row.bowler_name)
        roster_exists = conn.execute(
            "SELECT 1 FROM players WHERE team_id = ? LIMIT 1",
            (assignment.team_id,),
        ).fetchone()
        if roster_exists and canonical_name is None:
            report.rows_player_mismatch += 1
            unknown = (assignment.team_number, assignment.team_name, row.bowler_name)
            if unknown not in report.unknown_player_aliases:
                report.unknown_player_aliases.append(unknown)
            report.warnings.append(
                f"Team {assignment.team_name!r}: player name {row.bowler_name!r} "
                "does not match a registered name or known alias — row ignored"
            )
            continue
        if canonical_name is not None:
            from dataclasses import replace

            row = replace(row, bowler_name=canonical_name)

        teams_with_data.add((assignment.fixture_id, assignment.team_id))
        if _already_imported(conn, assignment.team_id, row.bowler_name, row.start_date):
            report.rows_duplicate += 1
            continue

        matched_by_team.setdefault(assignment.team_id, []).append(row)
        report.rows_new += 1
        report.to_insert.append((assignment, row))
        report.affected_fixture_ids.add(assignment.fixture_id)

    # Missing games: a fixture side whose lane contributed no matched rows.
    assignments_by_fixture: dict[int, list[LaneAssignment]] = {}
    for assignment in lanes.values():
        assignments_by_fixture.setdefault(assignment.fixture_id, []).append(assignment)
    for fixture_id, assignments in sorted(assignments_by_fixture.items()):
        for assignment in assignments:
            if (fixture_id, assignment.team_id) not in teams_with_data:
                report.warnings.append(
                    f"Fixture {fixture_id} ({assignment.team_name}): "
                    "no rows found in this export"
                )

    # Team size / play position sanity checks, per team that had any new rows.
    team_names_by_id = {a.team_id: a.team_name for a in lanes.values()}
    team_size_by_id = {a.team_id: a.team_size for a in lanes.values()}
    for team_id, team_rows in matched_by_team.items():
        positions = [r.play_position for r in team_rows]
        expected_size = team_size_by_id[team_id]
        if len(positions) != expected_size:
            report.warnings.append(
                f"{team_names_by_id[team_id]}: {len(positions)} new bowler rows this round, "
                f"expected {expected_size}"
            )
        if len(set(positions)) != len(positions):
            report.warnings.append(
                f"{team_names_by_id[team_id]}: duplicate play positions in this round's rows"
            )

    return report


def write_unknown_aliases(
    path: str | Path, division: str, report: ImportReport
) -> None:
    """Write unresolved centre names as rows ready for canonical player entry."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["division", "team_number", "team_name", "alias", "player_name"])
        for team_number, team_name, alias in report.unknown_player_aliases:
            writer.writerow([division, team_number, team_name, alias, ""])


def commit_import(conn: sqlite3.Connection, csv_path: str | Path, report: ImportReport) -> list[str]:
    """Write the new rows from a confirmed report, then recompute affected fixtures."""
    imported_at = datetime.now(timezone.utc).isoformat()
    source_file = str(csv_path)

    for assignment, row in report.to_insert:
        conn.execute(
            """
            INSERT INTO bowler_scores
                (fixture_id, team_id, play_position, bowler_name, scratch_score,
                 start_date, end_date, source_file, imported_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                assignment.fixture_id,
                assignment.team_id,
                row.play_position,
                row.bowler_name,
                row.scratch,
                row.start_date,
                row.end_date,
                source_file,
                imported_at,
            ),
        )
    conn.commit()

    notes: list[str] = []
    for fixture_id in sorted(report.affected_fixture_ids):
        note = recompute_fixture(conn, fixture_id)
        if note:
            notes.append(note)
    return notes
