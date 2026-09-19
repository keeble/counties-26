from counties26.scoring import (
    compute_fixture_result,
    compute_individual_points,
    compute_team_bonus,
)


def test_individual_points_win_loss():
    assert compute_individual_points(200, 190) == (10.0, 0.0)
    assert compute_individual_points(190, 200) == (0.0, 10.0)


def test_individual_points_tie_splits_bonus():
    assert compute_individual_points(180, 180) == (5.0, 5.0)


def test_team_bonus_win_loss_and_tie():
    assert compute_team_bonus(1000, 950, 50.0) == (50.0, 0.0)
    assert compute_team_bonus(950, 1000, 50.0) == (0.0, 50.0)
    assert compute_team_bonus(1000, 1000, 50.0) == (25.0, 25.0)


def test_fixture_result_worked_example():
    # Men's division: 5-a-side, every position on the left team beats its opposite
    # number 200 vs 190, so the left team should also take the 50-point team bonus.
    result = compute_fixture_result([200] * 5, [190] * 5, team_bonus_value=50.0)

    assert result.team_a_pinfall == 1000
    assert result.team_b_pinfall == 950
    assert result.team_a_bonus_points == [10.0] * 5
    assert result.team_b_bonus_points == [0.0] * 5
    assert result.team_a_team_bonus == 50.0
    assert result.team_b_team_bonus == 0.0
    assert result.team_a_total == 1100.0
    assert result.team_b_total == 950.0


def test_fixture_result_mixed_positions_and_tie():
    # Position 1: A wins, position 2: tie, position 3: B wins. Team totals tie overall.
    result = compute_fixture_result([200, 180, 150], [190, 180, 160], team_bonus_value=40.0)

    assert result.team_a_bonus_points == [10.0, 5.0, 0.0]
    assert result.team_b_bonus_points == [0.0, 5.0, 10.0]
    assert result.team_a_pinfall == result.team_b_pinfall == 530
    assert result.team_a_team_bonus == result.team_b_team_bonus == 20.0
    assert result.team_a_total == 530 + 15 + 20
    assert result.team_b_total == 530 + 15 + 20


def test_fixture_result_requires_equal_lineup_sizes():
    import pytest

    with pytest.raises(ValueError):
        compute_fixture_result([200, 190], [180], team_bonus_value=40.0)
