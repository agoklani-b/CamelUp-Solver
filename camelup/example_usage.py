from .state import GameState
from .engine import exact_probabilities, monte_carlo_probabilities, apply_move


def sample_state():
    gs = {
        "track_length": 16,
        "camels": [
            {"id": "A", "type": "racing", "position": 3, "stack_index": 0},
            {"id": "B", "type": "racing", "position": 3, "stack_index": 1},
            {"id": "C", "type": "crazy", "position": 2, "stack_index": 0},
        ],
        "tiles": [{"position": 4, "type": 1}, {"position": 2, "type": -1}],
        "remaining_dice": [{"camel_id": "A"}, {"camel_id": "B"}, {"camel_id": "C"}],
    }
    return GameState.from_dict(gs)


if __name__ == "__main__":
    s = sample_state()
    print("Exact (may be slow):")
    probs = exact_probabilities(s)
    print(probs)
    print("Monte Carlo quick estimate:")
    mc = monte_carlo_probabilities(s, trials=20000)
    print(mc)
