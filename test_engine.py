"""Comprehensive tests for the CamelUp engine."""
import pytest
from camelup.state import GameState
from camelup.engine import apply_move, evaluate_winner, exact_probabilities, monte_carlo_probabilities


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_state(camels, tiles=None, remaining=None, track_length=16):
    d = {
        "track_length": track_length,
        "camels": camels,
        "tiles": tiles or [],
        "remaining_dice": remaining or [],
    }
    return GameState.from_dict(d)


def stacks_dict(state):
    """Return {pos: [bottom..top]} from state.stacks."""
    return {pos: list(stack) for pos, stack in state.stacks}


# ---------------------------------------------------------------------------
# apply_move: basic movement
# ---------------------------------------------------------------------------

class TestBasicMovement:
    def test_racing_camel_moves_forward(self):
        s = make_state(
            camels=[{"id": "A", "type": "racing", "position": 3, "stack_index": 0}],
            remaining=[{"camel_id": "A"}],
        )
        s2 = apply_move(s, "A", 2)
        sd = stacks_dict(s2)
        assert sd == {5: ["A"]}

    def test_crazy_camel_moves_backward(self):
        s = make_state(
            camels=[{"id": "C", "type": "crazy", "position": 5, "stack_index": 0}],
            remaining=[{"camel_id": "C"}],
        )
        s2 = apply_move(s, "C", 2)
        sd = stacks_dict(s2)
        assert sd == {3: ["C"]}

    def test_racing_camel_roll_1(self):
        s = make_state(
            camels=[{"id": "A", "type": "racing", "position": 0, "stack_index": 0}],
            remaining=[{"camel_id": "A"}],
        )
        s2 = apply_move(s, "A", 1)
        assert stacks_dict(s2) == {1: ["A"]}

    def test_racing_camel_roll_3(self):
        s = make_state(
            camels=[{"id": "A", "type": "racing", "position": 10, "stack_index": 0}],
            remaining=[{"camel_id": "A"}],
        )
        s2 = apply_move(s, "A", 3)
        assert stacks_dict(s2) == {13: ["A"]}

    def test_crazy_boundary_clamp(self):
        """Crazy camel at pos 1 rolling 3 would go to -2, clamps to 0."""
        s = make_state(
            camels=[{"id": "C", "type": "crazy", "position": 1, "stack_index": 0}],
            remaining=[{"camel_id": "C"}],
        )
        s2 = apply_move(s, "C", 3)
        sd = stacks_dict(s2)
        assert 0 in sd and "C" in sd[0]

    def test_crazy_at_zero_stays(self):
        """Crazy camel at pos 0 cannot go further back, stays at 0."""
        s = make_state(
            camels=[{"id": "C", "type": "crazy", "position": 0, "stack_index": 0}],
            remaining=[{"camel_id": "C"}],
        )
        s2 = apply_move(s, "C", 2)
        sd = stacks_dict(s2)
        assert sd == {0: ["C"]}


# ---------------------------------------------------------------------------
# apply_move: stack carrying
# ---------------------------------------------------------------------------

class TestStackCarrying:
    def test_bottom_camel_carries_top(self):
        """A(bottom) B(top) at pos 3. A rolls 2 → both at pos 5, B still on top."""
        s = make_state(
            camels=[
                {"id": "A", "type": "racing", "position": 3, "stack_index": 0},
                {"id": "B", "type": "racing", "position": 3, "stack_index": 1},
            ],
            remaining=[{"camel_id": "A"}, {"camel_id": "B"}],
        )
        s2 = apply_move(s, "A", 2)
        sd = stacks_dict(s2)
        assert sd == {5: ["A", "B"]}  # A bottom, B top

    def test_top_camel_moves_alone(self):
        """B(top) rolls and leaves A(bottom) behind."""
        s = make_state(
            camels=[
                {"id": "A", "type": "racing", "position": 3, "stack_index": 0},
                {"id": "B", "type": "racing", "position": 3, "stack_index": 1},
            ],
            remaining=[{"camel_id": "A"}, {"camel_id": "B"}],
        )
        s2 = apply_move(s, "B", 2)
        sd = stacks_dict(s2)
        assert sd == {3: ["A"], 5: ["B"]}

    def test_three_camel_stack_carry(self):
        """Middle camel carries only itself and those above it."""
        s = make_state(
            camels=[
                {"id": "A", "type": "racing", "position": 2, "stack_index": 0},
                {"id": "B", "type": "racing", "position": 2, "stack_index": 1},
                {"id": "C", "type": "racing", "position": 2, "stack_index": 2},
            ],
            remaining=[{"camel_id": "A"}, {"camel_id": "B"}, {"camel_id": "C"}],
        )
        # B rolls: carries B and C, A stays
        s2 = apply_move(s, "B", 3)
        sd = stacks_dict(s2)
        assert sd == {2: ["A"], 5: ["B", "C"]}

    def test_crazy_carries_racing_above_it(self):
        """Crazy camel at bottom, racing on top — crazy carries racing backward."""
        s = make_state(
            camels=[
                {"id": "C", "type": "crazy",  "position": 5, "stack_index": 0},
                {"id": "A", "type": "racing", "position": 5, "stack_index": 1},
            ],
            remaining=[{"camel_id": "C"}, {"camel_id": "A"}],
        )
        s2 = apply_move(s, "C", 2)
        sd = stacks_dict(s2)
        # Both move to pos 3, order preserved: C bottom, A top
        assert sd == {3: ["C", "A"]}


# ---------------------------------------------------------------------------
# apply_move: landing on existing stack
# ---------------------------------------------------------------------------

class TestLandingOnStack:
    def test_land_on_top_of_existing(self):
        """A arrives at pos where B already is → A lands on top."""
        s = make_state(
            camels=[
                {"id": "A", "type": "racing", "position": 1, "stack_index": 0},
                {"id": "B", "type": "racing", "position": 3, "stack_index": 0},
            ],
            remaining=[{"camel_id": "A"}, {"camel_id": "B"}],
        )
        s2 = apply_move(s, "A", 2)  # A moves 1→3, lands on B
        sd = stacks_dict(s2)
        assert sd == {3: ["B", "A"]}  # B bottom, A on top

    def test_stack_merges_preserving_order(self):
        """A+B stack lands on C → [C, A, B] at destination."""
        s = make_state(
            camels=[
                {"id": "A", "type": "racing", "position": 1, "stack_index": 0},
                {"id": "B", "type": "racing", "position": 1, "stack_index": 1},
                {"id": "C", "type": "racing", "position": 3, "stack_index": 0},
            ],
            remaining=[{"camel_id": "A"}, {"camel_id": "B"}, {"camel_id": "C"}],
        )
        s2 = apply_move(s, "A", 2)  # A+B move from 1 to 3
        sd = stacks_dict(s2)
        assert sd == {3: ["C", "A", "B"]}


# ---------------------------------------------------------------------------
# apply_move: tile effects
# ---------------------------------------------------------------------------

class TestTileEffects:
    def test_oasis_moves_forward_one(self):
        """Oasis (+1) at pos 5: A rolls to 5 → bounces to 6, lands on top."""
        s = make_state(
            camels=[{"id": "A", "type": "racing", "position": 3, "stack_index": 0}],
            tiles=[{"position": 5, "type": 1}],
            remaining=[{"camel_id": "A"}],
        )
        s2 = apply_move(s, "A", 2)
        sd = stacks_dict(s2)
        assert sd == {6: ["A"]}

    def test_oasis_lands_on_top_of_existing(self):
        """Oasis at pos 5: A bounces to 6 where B is, lands on top of B."""
        s = make_state(
            camels=[
                {"id": "A", "type": "racing", "position": 3, "stack_index": 0},
                {"id": "B", "type": "racing", "position": 6, "stack_index": 0},
            ],
            tiles=[{"position": 5, "type": 1}],
            remaining=[{"camel_id": "A"}, {"camel_id": "B"}],
        )
        s2 = apply_move(s, "A", 2)
        sd = stacks_dict(s2)
        assert sd == {6: ["B", "A"]}

    def test_mirage_moves_back_one(self):
        """Mirage (-1) at pos 5: A rolls to 5 → goes to 4, lands under existing."""
        s = make_state(
            camels=[
                {"id": "A", "type": "racing", "position": 3, "stack_index": 0},
                {"id": "B", "type": "racing", "position": 4, "stack_index": 0},
            ],
            tiles=[{"position": 5, "type": -1}],
            remaining=[{"camel_id": "A"}, {"camel_id": "B"}],
        )
        s2 = apply_move(s, "A", 2)
        sd = stacks_dict(s2)
        # A goes to 4 and inserts UNDER B
        assert sd == {4: ["A", "B"]}

    def test_mirage_alone_at_destination(self):
        """Mirage at pos 5: A rolls there, goes to pos 4, no one at 4 → just A at 4."""
        s = make_state(
            camels=[{"id": "A", "type": "racing", "position": 3, "stack_index": 0}],
            tiles=[{"position": 5, "type": -1}],
            remaining=[{"camel_id": "A"}],
        )
        s2 = apply_move(s, "A", 2)
        sd = stacks_dict(s2)
        assert sd == {4: ["A"]}

    def test_mirage_clamps_to_zero(self):
        """Mirage at pos 1 with A rolling there → would go to 0, clamped."""
        s = make_state(
            camels=[{"id": "A", "type": "racing", "position": 0, "stack_index": 0}],
            tiles=[{"position": 1, "type": -1}],
            remaining=[{"camel_id": "A"}],
        )
        s2 = apply_move(s, "A", 1)
        sd = stacks_dict(s2)
        assert 0 in sd and "A" in sd[0]


# ---------------------------------------------------------------------------
# evaluate_winner
# ---------------------------------------------------------------------------

class TestEvaluateWinner:
    def test_single_racing_camel(self):
        s = make_state(camels=[{"id": "A", "type": "racing", "position": 5, "stack_index": 0}])
        assert evaluate_winner(s) == "A"

    def test_higher_position_wins(self):
        s = make_state(camels=[
            {"id": "A", "type": "racing", "position": 3, "stack_index": 0},
            {"id": "B", "type": "racing", "position": 7, "stack_index": 0},
        ])
        assert evaluate_winner(s) == "B"

    def test_top_of_stack_wins_tiebreak(self):
        s = make_state(camels=[
            {"id": "A", "type": "racing", "position": 5, "stack_index": 0},
            {"id": "B", "type": "racing", "position": 5, "stack_index": 1},
        ])
        assert evaluate_winner(s) == "B"  # B is on top

    def test_crazy_camel_on_top_does_not_win(self):
        """Bug: crazy camel on top of stack at max pos must NOT be declared winner."""
        s = make_state(camels=[
            {"id": "R", "type": "racing", "position": 5, "stack_index": 0},
            {"id": "C", "type": "crazy",  "position": 5, "stack_index": 1},
        ])
        winner = evaluate_winner(s)
        assert winner == "R", f"Expected racing camel R to win, got {winner}"

    def test_crazy_camel_at_max_pos_racing_wins_elsewhere(self):
        """Crazy camel at high pos, but racing camel further forward — racing wins."""
        s = make_state(camels=[
            {"id": "R", "type": "racing", "position": 8, "stack_index": 0},
            {"id": "C", "type": "crazy",  "position": 10, "stack_index": 0},
        ])
        # C is further along but crazy — R is the leading racing camel
        winner = evaluate_winner(s)
        assert winner == "R"

    def test_racing_wins_over_crazy_at_same_pos_below(self):
        """Racing camel above crazy at same max position wins."""
        s = make_state(camels=[
            {"id": "C", "type": "crazy",  "position": 5, "stack_index": 0},
            {"id": "R", "type": "racing", "position": 5, "stack_index": 1},
        ])
        assert evaluate_winner(s) == "R"


# ---------------------------------------------------------------------------
# exact_probabilities: analytical ground truth
# ---------------------------------------------------------------------------

class TestExactProbabilities:
    def test_single_camel_always_wins(self):
        """One racing camel, one die — always wins with prob 1.0."""
        s = make_state(
            camels=[{"id": "A", "type": "racing", "position": 0, "stack_index": 0}],
            remaining=[{"camel_id": "A"}],
        )
        probs = exact_probabilities(s)
        assert abs(probs.get("A", 0) - 1.0) < 1e-9

    def test_two_camels_analytical_result(self):
        """A at pos 0, B at pos 1, each with one die.

        Analytically derived:
          P(A wins) = 7/18 ≈ 0.3889
          P(B wins) = 11/18 ≈ 0.6111
        """
        s = make_state(
            camels=[
                {"id": "A", "type": "racing", "position": 0, "stack_index": 0},
                {"id": "B", "type": "racing", "position": 1, "stack_index": 0},
            ],
            remaining=[{"camel_id": "A"}, {"camel_id": "B"}],
        )
        probs = exact_probabilities(s)
        assert abs(probs.get("A", 0) - 7/18) < 1e-9, f"P(A)={probs.get('A',0)}, expected {7/18}"
        assert abs(probs.get("B", 0) - 11/18) < 1e-9, f"P(B)={probs.get('B',0)}, expected {11/18}"

    def test_probabilities_sum_to_one(self):
        s = make_state(
            camels=[
                {"id": "A", "type": "racing", "position": 2, "stack_index": 0},
                {"id": "B", "type": "racing", "position": 4, "stack_index": 0},
                {"id": "C", "type": "racing", "position": 3, "stack_index": 0},
            ],
            remaining=[{"camel_id": "A"}, {"camel_id": "B"}, {"camel_id": "C"}],
        )
        probs = exact_probabilities(s)
        assert abs(sum(probs.values()) - 1.0) < 1e-9

    def test_certain_winner_no_remaining_dice(self):
        """No dice left — winner is whoever is in the lead."""
        s = make_state(
            camels=[
                {"id": "A", "type": "racing", "position": 3, "stack_index": 0},
                {"id": "B", "type": "racing", "position": 7, "stack_index": 0},
            ],
            remaining=[],
        )
        probs = exact_probabilities(s)
        assert probs.get("B", 0) == 1.0
        assert probs.get("A", 0) == 0.0

    def test_crazy_camel_cannot_win(self):
        """Crazy camels should never appear as leg winners."""
        s = make_state(
            camels=[
                {"id": "R", "type": "racing", "position": 2, "stack_index": 0},
                {"id": "C", "type": "crazy",  "position": 8, "stack_index": 0},
            ],
            remaining=[{"camel_id": "R"}, {"camel_id": "C"}],
        )
        probs = exact_probabilities(s)
        assert probs.get("C", 0) == 0.0, f"Crazy camel C should not win, got P(C)={probs.get('C',0)}"
        assert abs(probs.get("R", 0) - 1.0) < 1e-9

    def test_oasis_affects_probabilities(self):
        """Oasis tile should influence outcomes — just check sums to 1 and no crash."""
        s = make_state(
            camels=[
                {"id": "A", "type": "racing", "position": 1, "stack_index": 0},
                {"id": "B", "type": "racing", "position": 3, "stack_index": 0},
            ],
            tiles=[{"position": 3, "type": 1}],
            remaining=[{"camel_id": "A"}, {"camel_id": "B"}],
        )
        probs = exact_probabilities(s)
        assert abs(sum(probs.values()) - 1.0) < 1e-9

    def test_mirage_affects_probabilities(self):
        """Mirage tile should influence outcomes — just check sums to 1 and no crash."""
        s = make_state(
            camels=[
                {"id": "A", "type": "racing", "position": 1, "stack_index": 0},
                {"id": "B", "type": "racing", "position": 3, "stack_index": 0},
            ],
            tiles=[{"position": 3, "type": -1}],
            remaining=[{"camel_id": "A"}, {"camel_id": "B"}],
        )
        probs = exact_probabilities(s)
        assert abs(sum(probs.values()) - 1.0) < 1e-9

    def test_finish_crossing_ends_leg_immediately(self):
        """When a racing camel crosses track_length the leg ends — remaining dice NOT rolled.

        State: R at 13, B at 14, track_length=16, remaining=[R, B].

        Key buggy branches without early termination:
          - R rolls 3 → R at 16 (finish). Correct: R wins. Buggy: B still rolls;
            B rolling 2 lands on top of R at 16 → B wins instead.
          - B rolls 2 → B at 16 (finish). Correct: B wins. Buggy: R still rolls;
            R rolling 3 → R at 16 on top of B → R wins instead.

        Analytically (with correct early termination):
          P(R wins) = 4/9,  P(B wins) = 5/9
        """
        s = make_state(
            camels=[
                {"id": "R", "type": "racing", "position": 13, "stack_index": 0},
                {"id": "B", "type": "racing", "position": 14, "stack_index": 0},
            ],
            remaining=[{"camel_id": "R"}, {"camel_id": "B"}],
            track_length=16,
        )
        probs = exact_probabilities(s)
        assert abs(probs.get("R", 0) - 4/9) < 1e-9, f"P(R)={probs.get('R',0):.6f}, expected {4/9:.6f}"
        assert abs(probs.get("B", 0) - 5/9) < 1e-9, f"P(B)={probs.get('B',0):.6f}, expected {5/9:.6f}"

    def test_finish_crossing_mc_consistent(self):
        """MC should agree with exact on the finish-crossing scenario within 3%."""
        s = make_state(
            camels=[
                {"id": "R", "type": "racing", "position": 13, "stack_index": 0},
                {"id": "B", "type": "racing", "position": 14, "stack_index": 0},
            ],
            remaining=[{"camel_id": "R"}, {"camel_id": "B"}],
            track_length=16,
        )
        probs = monte_carlo_probabilities(s, trials=50000)
        assert abs(probs.get("R", 0) - 4/9) < 0.03
        assert abs(probs.get("B", 0) - 5/9) < 0.03


# ---------------------------------------------------------------------------
# monte_carlo_probabilities: convergence
# ---------------------------------------------------------------------------

class TestMonteCarlo:
    def test_mc_single_camel_wins(self):
        s = make_state(
            camels=[{"id": "A", "type": "racing", "position": 0, "stack_index": 0}],
            remaining=[{"camel_id": "A"}],
        )
        probs = monte_carlo_probabilities(s, trials=5000)
        assert abs(probs.get("A", 0) - 1.0) < 1e-9

    def test_mc_matches_exact_within_tolerance(self):
        """MC should be within 3% of exact for the two-camel analytical case."""
        s = make_state(
            camels=[
                {"id": "A", "type": "racing", "position": 0, "stack_index": 0},
                {"id": "B", "type": "racing", "position": 1, "stack_index": 0},
            ],
            remaining=[{"camel_id": "A"}, {"camel_id": "B"}],
        )
        probs = monte_carlo_probabilities(s, trials=50000)
        assert abs(probs.get("A", 0) - 7/18) < 0.03
        assert abs(probs.get("B", 0) - 11/18) < 0.03

    def test_mc_sums_to_one(self):
        s = make_state(
            camels=[
                {"id": "A", "type": "racing", "position": 2, "stack_index": 0},
                {"id": "B", "type": "racing", "position": 4, "stack_index": 0},
            ],
            remaining=[{"camel_id": "A"}, {"camel_id": "B"}],
        )
        probs = monte_carlo_probabilities(s, trials=10000)
        assert abs(sum(probs.values()) - 1.0) < 1e-9
