# CamelUp Solver

A probability calculator for the board game Camel Up (2nd edition). Given a mid-game board state, it computes the odds of each racing camel winning the current leg.

No dependencies beyond the Python standard library.

## Running the GUI

```bash
python -m camelup.gui
```

## Using the GUI

1. Click a camel token in the palette to select it, then click a board tile to place it
2. Use **+1 Oasis** and **-1 Mirage** to place desert tiles (click to activate, then click a tile)
3. Right-click any board tile to remove the top camel or tile marker
4. Toggle off dice that have already been rolled this leg
5. Hit **Exact** or **Monte Carlo** to compute win probabilities

## Running tests

```bash
PYTHONPATH=. pytest test_engine.py -v
```

## Rules implemented

- Racing camels move forward; crazy camels (Bk, Wh) move backward
- A camel carries all camels stacked above it when it moves
- Oasis tiles move the landing camel one extra step forward (lands on top of any stack)
- Mirage tiles move the landing camel one step back (slides under any stack)
- Desert tiles cannot share a tile with a camel or be placed on adjacent tiles
- The leg ends immediately when any racing camel reaches or passes the finish line
