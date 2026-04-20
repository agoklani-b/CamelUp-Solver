import pytest

from camelup.state import GameState
from camelup.engine import apply_move, exact_probabilities, monte_carlo_probabilities


def test_stack_split_move_middle():
    # A bottom, B middle, C top at pos 3
    gs = {
        "track_length": 10,
        "camels": [
            {"id": "A", "type": "racing", "position": 3, "stack_index": 0},
            {"id": "B", "type": "racing", "position": 3, "stack_index": 1},
            {"id": "C", "type": "racing", "position": 3, "stack_index": 2},
        ],
        "tiles": [],
        "remaining_dice": [{"camel_id": "A"}, {"camel_id": "B"}, {"camel_id": "C"}],
    }
    s = GameState.from_dict(gs)
    s2 = apply_move(s, "B", 1)
    # After B moves by 1, B and C should be at pos 4 with B bottom, C top
    stacks = dict(s2.stacks)
    assert stacks[4] == ("B", "C")
    assert stacks[3] == ("A",)


def test_mirage_lands_under():
    # Setup so A moves to pos 2 (mirage) then back to pos 1 under existing stack B
    gs = {
        "track_length": 10,
        "camels": [
            {"id": "A", "type": "racing", "position": 0, "stack_index": 0},
            {"id": "B", "type": "racing", "position": 1, "stack_index": 0},
        ],
        "tiles": [{"position": 2, "type": -1}],
        "remaining_dice": [{"camel_id": "A"}, {"camel_id": "B"}],
    }
    s = GameState.from_dict(gs)
    s2 = apply_move(s, "A", 2)  # A moves to pos 2 (mirage) -> then back to 1 under existing stack B
    stacks = dict(s2.stacks)
    # After mirage, A should be under B at pos 1
    assert stacks[1] == ("A", "B")


def test_crazy_moves_backward_and_carries():
    gs = {
        "track_length": 10,
        "camels": [
            {"id": "R", "type": "racing", "position": 4, "stack_index": 0},
            {"id": "Cz", "type": "crazy", "position": 5, "stack_index": 0},
            {"id": "T", "type": "racing", "position": 5, "stack_index": 1},
        ],
        "tiles": [],
        "remaining_dice": [{"camel_id": "R"}, {"camel_id": "Cz"}, {"camel_id": "T"}],
    }
    s = GameState.from_dict(gs)
    # crazy camel Cz at pos5 bottom, carries T above when moving backward
    s2 = apply_move(s, "Cz", 2)
    stacks = dict(s2.stacks)
    # Cz moves backward 2 to pos3 carrying T
    assert stacks[3] == ("Cz", "T")


def test_exact_and_montecarlo_consistency():
    gs = {
        "track_length": 8,
        "camels": [
            {"id": "A", "type": "racing", "position": 0, "stack_index": 0},
            {"id": "B", "type": "racing", "position": 0, "stack_index": 1},
        ],
        "tiles": [],
        "remaining_dice": [{"camel_id": "A"}, {"camel_id": "B"}],
    }
    s = GameState.from_dict(gs)
    exact = exact_probabilities(s)
    mc = monte_carlo_probabilities(s, trials=2000)
    # both should produce probabilities summing to ~1
    assert abs(sum(exact.values()) - 1.0) < 1e-9
    assert abs(sum(mc.values()) - 1.0) < 1e-6
