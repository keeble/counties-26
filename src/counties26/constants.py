"""Tournament-wide constants for the two divisions."""

from __future__ import annotations

from dataclasses import dataclass

DIVISIONS = ("men", "women")


@dataclass(frozen=True)
class DivisionConfig:
    team_size: int
    team_bonus: float


DIVISION_CONFIG: dict[str, DivisionConfig] = {
    "women": DivisionConfig(team_size=4, team_bonus=40.0),
    "men": DivisionConfig(team_size=5, team_bonus=50.0),
}


def require_division(division: str) -> str:
    if division not in DIVISIONS:
        raise ValueError(f"division must be one of {DIVISIONS!r}, got {division!r}")
    return division
