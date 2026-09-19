"""Petersen-style points scoring engine.

Kept as pure functions (no I/O) so they're straightforward to unit test — this is the
correctness-critical part of the whole tool.
"""

from __future__ import annotations

from dataclasses import dataclass


def compute_individual_points(
    score_a: int, score_b: int, bonus: float = 10.0
) -> tuple[float, float]:
    """Bonus points for one positional 1v1 matchup, split evenly on a tie."""
    if score_a > score_b:
        return bonus, 0.0
    if score_b > score_a:
        return 0.0, bonus
    return bonus / 2, bonus / 2


def compute_team_bonus(
    total_a: int, total_b: int, bonus_value: float
) -> tuple[float, float]:
    """Team bonus for the higher combined pinfall, split evenly on a tie."""
    return compute_individual_points(total_a, total_b, bonus_value)


@dataclass(frozen=True)
class FixtureResult:
    team_a_bonus_points: list[float]
    team_b_bonus_points: list[float]
    team_a_pinfall: int
    team_b_pinfall: int
    team_a_team_bonus: float
    team_b_team_bonus: float
    team_a_total: float
    team_b_total: float


def compute_fixture_result(
    team_a_scores: list[int], team_b_scores: list[int], team_bonus_value: float
) -> FixtureResult:
    """Compute full match points for two teams' scratch scores, ordered by play position."""
    if len(team_a_scores) != len(team_b_scores):
        raise ValueError(
            f"Team lineups must be the same size to score a match "
            f"(got {len(team_a_scores)} vs {len(team_b_scores)})"
        )
    if not team_a_scores:
        raise ValueError("Cannot score a fixture with no bowlers")

    team_a_bonus_points: list[float] = []
    team_b_bonus_points: list[float] = []
    for score_a, score_b in zip(team_a_scores, team_b_scores):
        bonus_a, bonus_b = compute_individual_points(score_a, score_b)
        team_a_bonus_points.append(bonus_a)
        team_b_bonus_points.append(bonus_b)

    pinfall_a = sum(team_a_scores)
    pinfall_b = sum(team_b_scores)
    team_bonus_a, team_bonus_b = compute_team_bonus(pinfall_a, pinfall_b, team_bonus_value)

    total_a = pinfall_a + sum(team_a_bonus_points) + team_bonus_a
    total_b = pinfall_b + sum(team_b_bonus_points) + team_bonus_b

    return FixtureResult(
        team_a_bonus_points=team_a_bonus_points,
        team_b_bonus_points=team_b_bonus_points,
        team_a_pinfall=pinfall_a,
        team_b_pinfall=pinfall_b,
        team_a_team_bonus=team_bonus_a,
        team_b_team_bonus=team_bonus_b,
        team_a_total=total_a,
        team_b_total=total_b,
    )
