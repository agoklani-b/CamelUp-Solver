from typing import Dict, Tuple, List
from collections import defaultdict
import random

from .state import GameState


def _stacks_map_to_canonical(stacks_map: Dict[int, List[str]]) -> Tuple[Tuple[int, Tuple[str, ...]], ...]:
    return tuple(sorted(((pos, tuple(stack)) for pos, stack in stacks_map.items()), key=lambda x: x[0]))


def _find_camel(stacks_map: Dict[int, List[str]], camel_id: str):
    for pos, stack in stacks_map.items():
        if camel_id in stack:
            return pos, stack.index(camel_id)
    raise ValueError(f"Camel {camel_id} not found in any stack")


def apply_move(state: GameState, camel_id: str, roll_value: int) -> GameState:
    """Apply a single die move to the state and return a new GameState.

    Movement rules:
    - Moving camel carries itself + all camels above it
    - Racing camels move forward; crazy camels move backward
    - Tile effects (+1 oasis, -1 mirage) trigger once upon initial landing
    - Oasis: move forward 1 and land on top
    - Mirage: move back 1 and land under
    """
    track_length, stacks_map, camel_types, remaining, tiles_map = state.to_mutable()

    pos, idx = _find_camel(stacks_map, camel_id)
    ctype = camel_types[camel_id]
    direction = 1 if ctype == "racing" else -1

    stack = stacks_map[pos]
    moving = stack[idx:]
    below = stack[:idx]

    if below:
        stacks_map[pos] = below
    else:
        del stacks_map[pos]

    initial_new_pos = pos + direction * roll_value
    if initial_new_pos < 0:
        initial_new_pos = 0

    # Tile effect applies only once
    tile = tiles_map.get(initial_new_pos)
    final_under = False
    new_pos = initial_new_pos
    if tile is not None:
        if tile == 1:
            new_pos = initial_new_pos + 1
            final_under = False
        elif tile == -1:
            new_pos = initial_new_pos - 1
            final_under = True
        if new_pos < 0:
            new_pos = 0

    # Place moving stack at new_pos
    existing = stacks_map.get(new_pos, [])
    if final_under:
        # placed under existing stack
        new_stack = list(moving) + list(existing)
    else:
        # placed on top
        new_stack = list(existing) + list(moving)

    stacks_map[new_pos] = new_stack

    new_stacks = _stacks_map_to_canonical(stacks_map)
    new_state = GameState(track_length=track_length, stacks=new_stacks, camel_types=tuple(sorted(state.camel_types)), remaining_dice=tuple(sorted(state.remaining_dice)), tiles=tuple(sorted(state.tiles)))
    return new_state


def evaluate_winner(state: GameState) -> str:
    # Leg winner is the topmost RACING camel at the highest position occupied by racing camels.
    # Crazy camels cannot win a leg even if carried to a high position.
    camel_types = dict(state.camel_types)
    racing_stacks = [(pos, stack) for pos, stack in state.stacks
                     if any(camel_types.get(c) == "racing" for c in stack)]
    if not racing_stacks:
        raise ValueError("No racing camels on track")
    max_pos = max(pos for pos, _ in racing_stacks)
    for pos, stack in racing_stacks:
        if pos == max_pos:
            for c in reversed(stack):
                if camel_types.get(c) == "racing":
                    return c
    raise RuntimeError("Could not determine winner")


def _racing_crossed_finish(state: GameState) -> bool:
    """True if any racing camel is at or past track_length (leg ends immediately)."""
    camel_types = dict(state.camel_types)
    return any(
        pos >= state.track_length and any(camel_types.get(c) == "racing" for c in stack)
        for pos, stack in state.stacks
    )


def exact_probabilities(state: GameState, cancel_event=None) -> Dict[str, float]:
    """Exact enumeration with optional cancellation via threading.Event (pass event, set to cancel).

    If cancelled, a RuntimeError("Cancelled") is raised.
    """
    memo = {}

    def helper(s: GameState) -> Dict[str, float]:
        if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
            raise RuntimeError("Cancelled")
        key = s.canonical_key()
        if key in memo:
            return memo[key]
        # Leg ends when all dice rolled OR a racing camel crosses the finish line
        if not s.remaining_dice or _racing_crossed_finish(s):
            winner = evaluate_winner(s)
            memo[key] = {winner: 1.0}
            return memo[key]

        N = len(s.remaining_dice)
        acc = defaultdict(float)

        # each remaining die equally likely to be rolled next
        for i, die in enumerate(s.remaining_dice):
            if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
                raise RuntimeError("Cancelled")
            new_remaining = list(s.remaining_dice)
            new_remaining.pop(i)
            for roll in (1, 2, 3):
                if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
                    raise RuntimeError("Cancelled")
                p = (1.0 / N) * (1.0 / 3.0)
                moved = apply_move(s, die, roll)
                new_state = GameState(track_length=moved.track_length, stacks=moved.stacks, camel_types=moved.camel_types, remaining_dice=tuple(sorted(new_remaining)), tiles=moved.tiles)
                res = helper(new_state)
                for winner, wp in res.items():
                    acc[winner] += p * wp

        memo[key] = dict(acc)
        return memo[key]

    return helper(state)


def monte_carlo_probabilities(state: GameState, trials: int = 100000, cancel_event=None) -> Dict[str, float]:
    counts = defaultdict(int)
    for _ in range(trials):
        if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
            raise RuntimeError("Cancelled")
        track_length, stacks_map, camel_types, remaining, tiles_map = state.to_mutable()
        # random order of remaining dice
        order = list(remaining)
        random.shuffle(order)
        leg_over = False
        for die in order:
            roll = random.randint(1, 3)
            # apply move in-place using same logic as apply_move
            pos, idx = _find_camel(stacks_map, die)
            ctype = camel_types[die]
            direction = 1 if ctype == "racing" else -1
            stack = stacks_map[pos]
            moving = stack[idx:]
            below = stack[:idx]
            if below:
                stacks_map[pos] = below
            else:
                del stacks_map[pos]
            initial_new_pos = pos + direction * roll
            if initial_new_pos < 0:
                initial_new_pos = 0
            tile = tiles_map.get(initial_new_pos)
            final_under = False
            new_pos = initial_new_pos
            if tile is not None:
                if tile == 1:
                    new_pos = initial_new_pos + 1
                    final_under = False
                elif tile == -1:
                    new_pos = initial_new_pos - 1
                    final_under = True
                if new_pos < 0:
                    new_pos = 0
            existing = stacks_map.get(new_pos, [])
            if final_under:
                new_stack = list(moving) + list(existing)
            else:
                new_stack = list(existing) + list(moving)
            stacks_map[new_pos] = new_stack
            # Early termination: a racing camel crossed the finish line
            if any(p >= track_length and any(camel_types.get(c) == "racing" for c in s)
                   for p, s in stacks_map.items()):
                leg_over = True
                break

        # Determine winner: topmost racing camel at the highest position with a racing camel
        racing_positions = [(p, s) for p, s in stacks_map.items()
                            if any(camel_types.get(c) == "racing" for c in s)]
        max_pos = max(p for p, _ in racing_positions)
        winner = next(c for c in reversed(next(s for p, s in racing_positions if p == max_pos))
                      if camel_types.get(c) == "racing")
        counts[winner] += 1

    total = float(trials)
    return {k: v / total for k, v in counts.items()}
