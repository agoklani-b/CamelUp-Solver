from dataclasses import dataclass
from typing import Tuple, Dict, List


@dataclass(frozen=True)
class GameState:
    track_length: int
    # mapping position -> tuple of camel ids bottom->top
    stacks: Tuple[Tuple[int, Tuple[str, ...]], ...]
    camel_types: Tuple[Tuple[str, str], ...]  # tuple of (camel_id, type)
    remaining_dice: Tuple[str, ...]
    tiles: Tuple[Tuple[int, int], ...]  # tuple of (position, type) where type is +1 or -1

    def canonical_key(self):
        return (self.track_length, self.stacks, self.camel_types, self.remaining_dice, self.tiles)

    @staticmethod
    def from_dict(d: Dict) -> "GameState":
        track_length = d["track_length"]
        # build stacks mapping
        pos_map: Dict[int, List[str]] = {}
        for c in d["camels"]:
            pos_map.setdefault(c["position"], [])
        # ensure order by stack_index
        for c in sorted(d["camels"], key=lambda x: (x["position"], x["stack_index"])):
            pos_map[c["position"]].append(c["id"])
        stacks = tuple(sorted(((pos, tuple(stack)) for pos, stack in pos_map.items()), key=lambda x: x[0]))
        camel_types = tuple(sorted(((c["id"], c["type"]) for c in d["camels"]), key=lambda x: x[0]))
        remaining = tuple(sorted([x["camel_id"] for x in d.get("remaining_dice", [])]))
        tiles = tuple(sorted(((t["position"], t["type"]) for t in d.get("tiles", [])), key=lambda x: x[0]))
        return GameState(track_length=track_length, stacks=stacks, camel_types=camel_types, remaining_dice=remaining, tiles=tiles)

    def to_mutable(self):
        # returns convenient mutable structures for simulation
        stacks_map = {pos: list(stack) for pos, stack in self.stacks}
        camel_types = {cid: t for cid, t in self.camel_types}
        remaining = list(self.remaining_dice)
        tiles_map = {pos: t for pos, t in self.tiles}
        return self.track_length, stacks_map, camel_types, remaining, tiles_map
