"""Camel Up Solver GUI."""
import logging
import threading
import queue
import tkinter as tk
from tkinter import ttk
from typing import Dict, List, Optional, Tuple

from .state import GameState
from .engine import exact_probabilities, monte_carlo_probabilities

logging.basicConfig(
    filename="camelup_gui.log", level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
)

# ── Board geometry ───────────────────────────────────────────────────────────
TILE_W          = 60
TILE_H          = 130
BOARD_PAD_TOP   = 14
BOARD_DISPLAY_W = 900   # fixed viewport width — scrollbar handles overflow
CAMEL_R         = 14
CAMEL_SPACING   = 32

# ── Palette geometry ─────────────────────────────────────────────────────────
PAL_W   = 56   # width of one palette token slot
PAL_H   = 44   # height of one palette token slot
PAL_PAD = 7    # padding around tokens

# ── Colours ──────────────────────────────────────────────────────────────────
APP_BG       = "#ecf0f1"
PANEL_BG     = "#ecf0f1"
BOARD_BG     = "#ffffff"
TILE_BG      = "#fdfbe4"
TILE_ALT_BG  = "#f5f0c8"
OASIS_COLOR  = "#27ae60"
MIRAGE_COLOR = "#e74c3c"
SEL_COLOR    = "#f39c12"   # gold — selection highlight

FONT_NORMAL = ("Helvetica", 10)
FONT_BOLD   = ("Helvetica", 10, "bold")
FONT_TITLE  = ("Helvetica", 15, "bold")
FONT_SMALL  = ("Helvetica", 8)

# ── Standard camel definitions: (id, type, fill, text_color) ─────────────────
STANDARD_CAMELS: List[Tuple[str, str, str, str]] = [
    ("R",  "racing", "#e74c3c", "white"),
    ("B",  "racing", "#3498db", "white"),
    ("G",  "racing", "#27ae60", "white"),
    ("Y",  "racing", "#f39c12", "#2c3e50"),
    ("P",  "racing", "#8e44ad", "white"),
    ("Bk", "crazy",  "#2c3e50", "white"),
    ("Wh", "crazy",  "#bdc3c7", "#2c3e50"),
]

_CAMEL_META = {cid: (ctype, fill, tc) for cid, ctype, fill, tc in STANDARD_CAMELS}


def _muted(hex_color: str, bg: str = APP_BG, alpha: float = 0.3) -> str:
    """Blend hex_color toward bg — used to dim placed camels in the palette."""
    r1, g1, b1 = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    r2, g2, b2 = int(bg[1:3], 16), int(bg[3:5], 16), int(bg[5:7], 16)
    r = int(r1 * alpha + r2 * (1 - alpha))
    g = int(g1 * alpha + g2 * (1 - alpha))
    b = int(b1 * alpha + b2 * (1 - alpha))
    return f"#{r:02x}{g:02x}{b:02x}"


# ─────────────────────────────────────────────────────────────────────────────

class CamelUpGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Camel Up Solver")
        self.root.configure(bg=APP_BG)
        self.root.resizable(False, False)   # window size never changes

        # ── Authoritative board state ──────────────────────────────────────
        # None means camel is not yet placed on the board
        self.camel_data: Dict[str, Optional[dict]] = {
            cid: None for cid, *_ in STANDARD_CAMELS
        }
        self.tile_data:  Dict[int, int] = {}
        self.track_length: int = 16

        # ── Solver ────────────────────────────────────────────────────────
        self.result_q: queue.Queue = queue.Queue()
        self.cancel_event = threading.Event()
        self.solver_thread: Optional[threading.Thread] = None

        # ── Interaction mode ───────────────────────────────────────────────
        # "place_camel" | "oasis" | "mirage" | None
        self.mode: Optional[str] = None
        self.selected_cid: Optional[str] = None

        # ── Remaining-dice toggle buttons (built when camels placed/removed) ─
        self.dice_vars: Dict[str, tk.BooleanVar] = {
            cid: tk.BooleanVar(value=True) for cid, *_ in STANDARD_CAMELS
        }
        self.dice_btns: Dict[str, tk.Button] = {}

        # Tile-mode buttons (kept so we can toggle their relief)
        self._oasis_btn:  Optional[tk.Button] = None
        self._mirage_btn: Optional[tk.Button] = None

        self._build_ui()
        self.root.after(200, self._poll_results)

    # ════════════════════════════════════════════════════════════════════════
    # UI construction
    # ════════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        tk.Label(
            self.root, text="Camel Up Solver", font=FONT_TITLE,
            bg=APP_BG, fg="#2c3e50", pady=6,
        ).grid(row=0, column=0, columnspan=2, padx=10)

        # ── Board (full-width, scrollable) ────────────────────────────────
        board_outer = tk.Frame(self.root, bg=APP_BG)
        board_outer.grid(row=1, column=0, columnspan=2, padx=10, pady=(0, 4), sticky="ew")

        canvas_h = TILE_H + BOARD_PAD_TOP + 24
        self.board_canvas = tk.Canvas(
            board_outer, width=BOARD_DISPLAY_W, height=canvas_h,
            bg=BOARD_BG, highlightthickness=1, highlightbackground="#bdc3c7",
        )
        h_scroll = ttk.Scrollbar(board_outer, orient="horizontal",
                                  command=self.board_canvas.xview)
        self.board_canvas.configure(xscrollcommand=h_scroll.set)
        self.board_canvas.grid(row=0, column=0, sticky="ew")
        h_scroll.grid(row=1, column=0, sticky="ew")

        tk.Label(
            board_outer,
            text="Left-click to place selected camel or tile  ·  Right-click to remove topmost camel or tile marker",
            font=FONT_SMALL, bg=APP_BG, fg="#7f8c8d",
        ).grid(row=2, column=0, sticky="w", pady=2)

        self.board_canvas.bind("<Button-1>", self._board_left_click)
        self.board_canvas.bind("<Button-3>", self._board_right_click)

        # ── Setup panel (bottom-left) ─────────────────────────────────────
        setup = tk.Frame(self.root, bg=PANEL_BG, padx=10, pady=6)
        setup.grid(row=2, column=0, sticky="nw")
        self._build_setup_panel(setup)

        # ── Solver panel (bottom-right) ───────────────────────────────────
        solver = tk.Frame(self.root, bg=PANEL_BG, padx=10, pady=6)
        solver.grid(row=2, column=1, sticky="nw")
        self._build_solver_panel(solver)

        self._render_board()

    # ── Setup panel ──────────────────────────────────────────────────────────

    def _build_setup_panel(self, f: tk.Frame):
        r = 0

        # Section: Camel Palette
        tk.Label(f, text="Camels", font=FONT_BOLD, bg=PANEL_BG, fg="#2c3e50").grid(
            row=r, column=0, sticky="w"); r += 1
        tk.Label(
            f, font=FONT_SMALL, bg=PANEL_BG, fg="#7f8c8d",
            text="Click a camel to select it, then click a board tile to place it.\n"
                 "Click a placed camel again to pick it up and reposition it.",
        ).grid(row=r, column=0, sticky="w"); r += 1

        n = len(STANDARD_CAMELS)
        pal_canvas_w = PAL_PAD + n * (PAL_W + PAL_PAD)
        pal_canvas_h = PAL_H + PAL_PAD * 2
        self.palette_canvas = tk.Canvas(
            f, width=pal_canvas_w, height=pal_canvas_h,
            bg=PANEL_BG, highlightthickness=0,
        )
        self.palette_canvas.grid(row=r, column=0, sticky="w", pady=4); r += 1
        self.palette_canvas.bind("<Button-1>", self._palette_click)
        self._render_palette()

        self._sep(f, r); r += 1

        # Section: Desert Tiles
        tk.Label(f, text="Desert Tiles", font=FONT_BOLD, bg=PANEL_BG, fg="#2c3e50").grid(
            row=r, column=0, sticky="w"); r += 1
        tk.Label(
            f, font=FONT_SMALL, bg=PANEL_BG, fg="#7f8c8d",
            text="Click a tile button to activate, then click a board tile to place it.\n"
                 "Right-click any board tile to remove its tile marker.",
        ).grid(row=r, column=0, sticky="w"); r += 1

        tile_row = tk.Frame(f, bg=PANEL_BG)
        tile_row.grid(row=r, column=0, sticky="w", pady=4); r += 1
        self._oasis_btn = tk.Button(
            tile_row, text="+1 Oasis", bg=OASIS_COLOR, fg="white",
            font=FONT_NORMAL, relief="flat", padx=8, pady=4, cursor="hand2",
            command=lambda: self._activate_tile(1),
        )
        self._oasis_btn.pack(side="left", padx=(0, 6))
        self._mirage_btn = tk.Button(
            tile_row, text="-1 Mirage", bg=MIRAGE_COLOR, fg="white",
            font=FONT_NORMAL, relief="flat", padx=8, pady=4, cursor="hand2",
            command=lambda: self._activate_tile(-1),
        )
        self._mirage_btn.pack(side="left", padx=(0, 6))
        tk.Button(
            tile_row, text="Clear Tiles", bg="#95a5a6", fg="white",
            font=FONT_NORMAL, relief="flat", padx=8, pady=4, cursor="hand2",
            command=self._clear_tiles,
        ).pack(side="left")

        self._sep(f, r); r += 1

        # Section: Track / Reset
        cfg = tk.Frame(f, bg=PANEL_BG)
        cfg.grid(row=r, column=0, sticky="w")
        tk.Label(cfg, text="Track length:", bg=PANEL_BG, font=FONT_NORMAL).pack(side="left")
        self.track_len_var = tk.IntVar(value=16)
        tk.Spinbox(
            cfg, from_=4, to=32, textvariable=self.track_len_var, width=5,
            command=self._on_track_len_change,
        ).pack(side="left", padx=6)
        tk.Button(
            cfg, text="Reset Board", bg="#bdc3c7", fg="#2c3e50",
            font=FONT_NORMAL, relief="flat", padx=8, pady=3, cursor="hand2",
            command=self._reset,
        ).pack(side="left", padx=4)

    # ── Solver panel ─────────────────────────────────────────────────────────

    def _build_solver_panel(self, f: tk.Frame):
        r = 0

        # Section: Remaining Dice
        tk.Label(f, text="Remaining Dice", font=FONT_BOLD, bg=PANEL_BG, fg="#2c3e50").grid(
            row=r, column=0, sticky="w"); r += 1
        tk.Label(
            f, font=FONT_SMALL, bg=PANEL_BG, fg="#7f8c8d",
            text="Toggle off camels whose die has already been rolled this leg.",
        ).grid(row=r, column=0, sticky="w"); r += 1
        self.dice_row_frame = tk.Frame(f, bg=PANEL_BG)
        self.dice_row_frame.grid(row=r, column=0, sticky="w", pady=4); r += 1
        self._rebuild_dice_row()

        self._sep(f, r); r += 1

        # Section: Solver
        tk.Label(f, text="Compute Odds", font=FONT_BOLD, bg=PANEL_BG, fg="#2c3e50").grid(
            row=r, column=0, sticky="w"); r += 1
        btn_row = tk.Frame(f, bg=PANEL_BG)
        btn_row.grid(row=r, column=0, sticky="w", pady=4); r += 1
        tk.Button(
            btn_row, text="Exact", command=self.run_exact,
            bg="#2c3e50", fg="white", font=FONT_BOLD,
            relief="flat", padx=10, pady=5, cursor="hand2",
        ).pack(side="left", padx=(0, 4))
        tk.Button(
            btn_row, text="Monte Carlo", command=self.run_mc,
            bg="#8e44ad", fg="white", font=FONT_BOLD,
            relief="flat", padx=10, pady=5, cursor="hand2",
        ).pack(side="left", padx=(0, 4))
        tk.Button(
            btn_row, text="Cancel", command=self.cancel_solver,
            bg="#c0392b", fg="white", font=FONT_NORMAL,
            relief="flat", padx=10, pady=5, cursor="hand2",
        ).pack(side="left")

        self.status_var = tk.StringVar(value="Ready")
        tk.Label(
            f, textvariable=self.status_var, bg=PANEL_BG, fg="#7f8c8d",
            font=("Helvetica", 9, "italic"), wraplength=380, justify="left",
        ).grid(row=r, column=0, sticky="w", pady=2); r += 1

        self._sep(f, r); r += 1

        # Section: Results
        tk.Label(f, text="Win Probabilities", font=FONT_BOLD, bg=PANEL_BG, fg="#2c3e50").grid(
            row=r, column=0, sticky="w"); r += 1
        self.results_canvas = tk.Canvas(
            f, width=450, height=8,
            bg=BOARD_BG, highlightthickness=1, highlightbackground="#bdc3c7",
        )
        self.results_canvas.grid(row=r, column=0, sticky="w", pady=(2, 0))
        self._render_results({})

    def _sep(self, parent: tk.Frame, row: int):
        ttk.Separator(parent, orient="horizontal").grid(
            row=row, column=0, columnspan=4, sticky="ew", pady=5)

    # ════════════════════════════════════════════════════════════════════════
    # Rendering
    # ════════════════════════════════════════════════════════════════════════

    def _render_palette(self):
        c = self.palette_canvas
        c.delete("all")
        for i, (cid, _, fill, text_col) in enumerate(STANDARD_CAMELS):
            cx = PAL_PAD + i * (PAL_W + PAL_PAD) + PAL_W / 2
            cy = PAL_PAD + PAL_H / 2
            placed   = self.camel_data[cid] is not None
            selected = self.selected_cid == cid
            display_fill = _muted(fill) if placed else fill

            if selected:
                c.create_rectangle(
                    cx - PAL_W / 2 - 3, cy - PAL_H / 2 - 3,
                    cx + PAL_W / 2 + 3, cy + PAL_H / 2 + 3,
                    fill=SEL_COLOR, outline="",
                )

            c.create_oval(
                cx - PAL_W / 2 + 3, cy - PAL_H / 2 + 3,
                cx + PAL_W / 2 - 3, cy + PAL_H / 2 - 3,
                fill=display_fill,
                outline=SEL_COLOR if selected else ("#888" if placed else "#2c3e50"),
                width=3 if selected else 2,
            )

            c.create_text(
                cx, cy, text=cid,
                font=("Helvetica", 9, "bold"),
                fill=text_col if not placed else "#aaaaaa",
            )

    def _render_board(self):
        c = self.board_canvas
        c.delete("all")
        full_w = TILE_W * self.track_length
        full_h = TILE_H + BOARD_PAD_TOP + 24
        # Update scrollregion only — canvas widget size stays fixed → no window resize
        c.configure(scrollregion=(0, 0, full_w, full_h))
        for i in range(self.track_length):
            self._draw_tile(i)

    def _draw_tile(self, pos: int):
        c = self.board_canvas
        x0, y0 = pos * TILE_W, BOARD_PAD_TOP
        x1, y1 = x0 + TILE_W, y0 + TILE_H
        bg = TILE_ALT_BG if pos % 2 else TILE_BG

        c.create_rectangle(x0 + 1, y0, x1 - 1, y1, fill=bg, outline="#bdc3c7", width=1)
        c.create_text(x0 + TILE_W / 2, y1 + 12, text=str(pos), font=FONT_SMALL, fill="#7f8c8d")

        # Desert tile marker
        if pos in self.tile_data:
            ttype = self.tile_data[pos]
            col   = OASIS_COLOR if ttype == 1 else MIRAGE_COLOR
            label = "+1" if ttype == 1 else "-1"
            mx, my = x0 + TILE_W / 2, y0 + 15
            c.create_rectangle(mx - 16, my - 11, mx + 16, my + 11, fill=col, outline="")
            c.create_text(mx, my, text=label, fill="white", font=FONT_BOLD)

        # Camel tokens — drawn bottom (si=0) up
        camels_here = sorted(
            [(cid, d) for cid, d in self.camel_data.items()
             if d is not None and d["pos"] == pos],
            key=lambda x: x[1]["stack_index"],
        )
        for cid, d in camels_here:
            _, fill, text_col = _CAMEL_META[cid]
            cx = x0 + TILE_W / 2
            cy = y1 - CAMEL_R - 4 - d["stack_index"] * CAMEL_SPACING
            c.create_oval(
                cx - CAMEL_R, cy - CAMEL_R, cx + CAMEL_R, cy + CAMEL_R,
                fill=fill, outline="#2c3e50", width=1,
            )
            c.create_text(cx, cy, text=cid, font=("Helvetica", 8, "bold"), fill=text_col)

    def _rebuild_dice_row(self):
        for w in self.dice_row_frame.winfo_children():
            w.destroy()
        self.dice_btns.clear()
        any_placed = False
        for cid, _, fill, text_col in STANDARD_CAMELS:
            if self.camel_data[cid] is None:
                continue
            any_placed = True
            b = tk.Button(
                self.dice_row_frame, text=cid,
                font=("Helvetica", 9, "bold"), relief="flat",
                padx=6, pady=4, cursor="hand2",
                command=lambda c=cid: self._toggle_die(c),
            )
            b.pack(side="left", padx=2)
            self.dice_btns[cid] = b
            self._update_die_btn(cid)
        if not any_placed:
            tk.Label(
                self.dice_row_frame, text="No camels placed yet.",
                bg=PANEL_BG, fg="#7f8c8d", font=FONT_SMALL,
            ).pack(side="left")

    def _toggle_die(self, cid: str):
        self.dice_vars[cid].set(not self.dice_vars[cid].get())
        self._update_die_btn(cid)

    def _update_die_btn(self, cid: str):
        btn = self.dice_btns.get(cid)
        if not btn:
            return
        _, fill, text_col = _CAMEL_META[cid]
        if self.dice_vars[cid].get():
            btn.configure(bg=fill, fg=text_col)
        else:
            btn.configure(bg="#cccccc", fg="#888888")

    def _render_results(self, probs: dict):
        c = self.results_canvas
        c.delete("all")
        if not probs:
            c.configure(height=30)
            c.create_text(10, 15, text="No results yet - run a solver.",
                          anchor="w", font=FONT_NORMAL, fill="#7f8c8d")
            return

        # Filter to racing camels that are actually placed
        items = [
            (cid, p) for cid, p in probs.items()
            if self.camel_data.get(cid) is not None
            and _CAMEL_META.get(cid, ("racing",))[0] == "racing"
        ]
        # Fallback: show anything returned
        if not items:
            items = [(cid, p) for cid, p in probs.items() if self.camel_data.get(cid) is not None]
        items.sort(key=lambda x: x[1], reverse=True)

        row_h    = 32
        bar_x0   = 56
        bar_max_w = 310
        c.configure(height=len(items) * row_h + 12)

        for i, (cid, p) in enumerate(items):
            y = 10 + i * row_h
            _, fill, _ = _CAMEL_META.get(cid, ("racing", "#888888", "white"))
            c.create_rectangle(8, y + 4, 24, y + 24, fill=fill, outline="#2c3e50", width=1)
            c.create_text(32, y + 14, text=cid, anchor="w", font=FONT_BOLD, fill="#2c3e50")
            c.create_rectangle(bar_x0, y + 6, bar_x0 + bar_max_w, y + 26,
                               fill="#ecf0f1", outline="#bdc3c7", width=1)
            bar_w = int(p * bar_max_w)
            if bar_w > 0:
                c.create_rectangle(bar_x0, y + 6, bar_x0 + bar_w, y + 26,
                                   fill=fill, outline="")
            c.create_text(bar_x0 + bar_max_w + 8, y + 14,
                          text=f"{p * 100:.1f}%", anchor="w", font=FONT_BOLD, fill="#2c3e50")

    # ════════════════════════════════════════════════════════════════════════
    # Interaction modes
    # ════════════════════════════════════════════════════════════════════════

    def _set_mode(self, mode: Optional[str], msg: str = ""):
        self.mode = mode
        self.board_canvas.configure(cursor="crosshair" if mode else "arrow")
        self.status_var.set(msg or "Ready")
        # Visual indicator on tile mode buttons
        if self._oasis_btn:
            self._oasis_btn.configure(relief="sunken" if mode == "oasis" else "flat")
        if self._mirage_btn:
            self._mirage_btn.configure(relief="sunken" if mode == "mirage" else "flat")

    def _palette_click(self, event):
        x = event.x
        for i, (cid, *_) in enumerate(STANDARD_CAMELS):
            lx = PAL_PAD + i * (PAL_W + PAL_PAD)
            if lx <= x <= lx + PAL_W:
                if self.selected_cid == cid:
                    # Deselect
                    self.selected_cid = None
                    self._set_mode(None)
                else:
                    self.selected_cid = cid
                    self._set_mode("place_camel", f"Click a board tile to place '{cid}'")
                    # Deactivate tile modes
                    if self._oasis_btn:  self._oasis_btn.configure(relief="flat")
                    if self._mirage_btn: self._mirage_btn.configure(relief="flat")
                self._render_palette()
                return

    def _activate_tile(self, ttype: int):
        m     = "oasis" if ttype == 1 else "mirage"
        label = "Oasis (+1)" if ttype == 1 else "Mirage (-1)"
        if self.mode == m:
            # Toggle off
            self._set_mode(None)
        else:
            # Deselect any camel
            self.selected_cid = None
            self._render_palette()
            self._set_mode(m, f"Click a board tile to place a {label}")

    # ── Board clicks ─────────────────────────────────────────────────────────

    def _board_left_click(self, event):
        # Translate viewport x to canvas x (handles scroll offset)
        cx       = self.board_canvas.canvasx(event.x)
        tile_idx = max(0, min(int(cx // TILE_W), self.track_length - 1))

        if self.mode == "place_camel" and self.selected_cid:
            self._do_place_camel(self.selected_cid, tile_idx)
        elif self.mode in ("oasis", "mirage"):
            ttype = 1 if self.mode == "oasis" else -1
            self._do_place_tile(tile_idx, ttype)
        self._render_board()

    def _board_right_click(self, event):
        cx       = self.board_canvas.canvasx(event.x)
        tile_idx = max(0, min(int(cx // TILE_W), self.track_length - 1))
        if tile_idx in self.tile_data:
            del self.tile_data[tile_idx]
        else:
            self._do_remove_topmost_camel(tile_idx)
        self._render_board()
        self._render_palette()

    # ── State mutations ───────────────────────────────────────────────────────

    def _do_place_camel(self, cid: str, pos: int):
        if pos in self.tile_data:
            label = "Oasis" if self.tile_data[pos] == 1 else "Mirage"
            self.status_var.set(f"Tile {pos} has a {label} - camels cannot share a desert tile.")
            return
        # Pick up from old position if already placed
        old = self.camel_data[cid]
        if old is not None:
            self.camel_data[cid] = None
            self._reindex_at(old["pos"])

        stack_index = sum(1 for d in self.camel_data.values() if d is not None and d["pos"] == pos)
        ctype, _, _ = _CAMEL_META[cid]
        self.camel_data[cid] = {"pos": pos, "type": ctype, "stack_index": stack_index}

        self.selected_cid = None
        self._set_mode(None)
        self._render_palette()
        self._rebuild_dice_row()
        logging.info("Placed %s at pos %d idx %d", cid, pos, stack_index)

    def _do_place_tile(self, pos: int, ttype: int):
        if any(d is not None and d["pos"] == pos for d in self.camel_data.values()):
            self.status_var.set(f"Tile {pos} has camels on it - desert tiles cannot share a tile with a camel.")
            return
        for nb in (pos - 1, pos + 1):
            if nb in self.tile_data:
                ntype = "Oasis" if self.tile_data[nb] == 1 else "Mirage"
                self.status_var.set(f"Tile {nb} already has a {ntype} - desert tiles cannot be on adjacent tiles.")
                return
        self.tile_data[pos] = ttype
        logging.info("Placed tile %+d at pos %d", ttype, pos)

    def _do_remove_topmost_camel(self, pos: int):
        camels_at = sorted(
            [(cid, d) for cid, d in self.camel_data.items() if d is not None and d["pos"] == pos],
            key=lambda x: x[1]["stack_index"], reverse=True,
        )
        if not camels_at:
            return
        top_cid, _ = camels_at[0]
        self.camel_data[top_cid] = None
        self._reindex_at(pos)
        self._rebuild_dice_row()

    def _reindex_at(self, pos: int):
        remaining = sorted(
            [(cid, d) for cid, d in self.camel_data.items() if d is not None and d["pos"] == pos],
            key=lambda x: x[1]["stack_index"],
        )
        for new_idx, (cid, _) in enumerate(remaining):
            self.camel_data[cid]["stack_index"] = new_idx

    def _clear_tiles(self):
        self.tile_data.clear()
        self._render_board()

    def _on_track_len_change(self):
        self.track_length = int(self.track_len_var.get())
        self._render_board()   # only updates scrollregion — window stays fixed

    def _reset(self):
        self.camel_data = {cid: None for cid, *_ in STANDARD_CAMELS}
        self.tile_data.clear()
        for var in self.dice_vars.values():
            var.set(True)
        self.selected_cid = None
        self._set_mode(None)
        self._render_palette()
        self._rebuild_dice_row()
        self._render_board()
        self._render_results({})

    # ════════════════════════════════════════════════════════════════════════
    # Solver
    # ════════════════════════════════════════════════════════════════════════

    def _build_state_dict(self) -> dict:
        camels = [
            {"id": cid, "type": d["type"], "position": d["pos"], "stack_index": d["stack_index"]}
            for cid, d in self.camel_data.items() if d is not None
        ]
        tiles    = [{"position": pos, "type": t} for pos, t in self.tile_data.items()]
        remaining = [
            {"camel_id": cid} for cid, var in self.dice_vars.items()
            if var.get() and self.camel_data[cid] is not None
        ]
        return {"track_length": self.track_length, "camels": camels,
                "tiles": tiles, "remaining_dice": remaining}

    def _run_solver(self, label: str, fn, *extra_args):
        if not any(d is not None for d in self.camel_data.values()):
            self.status_var.set("Place at least one camel before running the solver.")
            return
        d     = self._build_state_dict()
        state = GameState.from_dict(d)
        logging.debug("Built GameState for %s: %s", label, d)
        self._set_mode(None)
        self.status_var.set(f"Running {label}…")
        self.cancel_event.clear()

        def worker():
            try:
                res = fn(state, *extra_args, cancel_event=self.cancel_event)
                self.result_q.put((True, res))
            except Exception as e:
                logging.exception("%s error", label)
                self.result_q.put((False, str(e)))

        self.solver_thread = threading.Thread(target=worker, daemon=True)
        self.solver_thread.start()

    def run_exact(self):
        self._run_solver("Exact", exact_probabilities)

    def run_mc(self):
        self._run_solver("Monte Carlo", monte_carlo_probabilities, 100000)

    def cancel_solver(self):
        if self.solver_thread and self.solver_thread.is_alive():
            self.cancel_event.set()
            self.status_var.set("Cancelling…")
        else:
            self.status_var.set("No active solver to cancel.")

    def _poll_results(self):
        try:
            ok, payload = self.result_q.get_nowait()
            if ok:
                self.status_var.set("Done.")
                self._render_results(payload)
            else:
                self.status_var.set(f"Error: {payload}")
                self._render_results({})
        except queue.Empty:
            pass
        self.root.after(200, self._poll_results)


# ════════════════════════════════════════════════════════════════════════════
# Entry point
# ════════════════════════════════════════════════════════════════════════════

def run_app():
    root = tk.Tk()
    CamelUpGUI(root)
    root.mainloop()


if __name__ == "__main__":
    run_app()
