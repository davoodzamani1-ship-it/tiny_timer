#!/usr/bin/env python3
"""Tiny Timer — multiple floating timer tiles."""

import math
import os
import struct
import subprocess
import tempfile
import threading
import tkinter as tk
import wave
from tkinter import colorchooser

# ── Palette ───────────────────────────────────────────────────────────────────
TILE_COLORS = [
    "#FF6B6B",  # coral
    "#4ECDC4",  # teal
    "#A855F7",  # violet
    "#FF8C42",  # orange
    "#45B7D1",  # sky blue
    "#6BCB77",  # green
    "#FF6B9D",  # hot pink
    "#FFD93D",  # yellow
]

PANEL_BG  = "#16213e"
PANEL_FG  = "#eaeaea"
PANEL_ACC = "#4ECDC4"

# ── Global app settings ───────────────────────────────────────────────────────
_settings = {"default_sound": "Soft Bell"}

# ── Sound definitions ─────────────────────────────────────────────────────────
SOUND_NAMES = ["Soft Bell", "Gentle Chime", "Marimba", "Soft Ping", "Wind Chime"]


def _generate_sound(name: str) -> list:
    """Return a list of 16-bit signed int samples for the named sound."""
    sr = 44100

    if name == "Soft Bell":
        # Pure sine, C5, long gentle decay
        dur, freq, amp, decay = 1.2, 523, 0.50, 3.5
        n = int(sr * dur)
        return [
            int(32767 * amp * math.exp(-i / sr * decay)
                * math.sin(2 * math.pi * freq * i / sr))
            for i in range(n)
        ]

    if name == "Gentle Chime":
        # Two-tone perfect fifth (C5 + G5), smooth fade
        dur, f1, f2, amp, decay = 0.9, 523, 784, 0.40, 4.0
        n = int(sr * dur)
        return [
            int(32767 * amp * math.exp(-i / sr * decay)
                * (0.65 * math.sin(2 * math.pi * f1 * i / sr)
                   + 0.35 * math.sin(2 * math.pi * f2 * i / sr)))
            for i in range(n)
        ]

    if name == "Marimba":
        # Fundamental + 2nd/3rd harmonics, warm woody tone
        dur, freq, amp, decay = 0.7, 440, 0.45, 6.0
        n = int(sr * dur)
        return [
            int(32767 * amp * math.exp(-i / sr * decay)
                * (0.60 * math.sin(2 * math.pi * freq * i / sr)
                   + 0.30 * math.sin(2 * math.pi * 2 * freq * i / sr)
                   + 0.10 * math.sin(2 * math.pi * 3 * freq * i / sr)))
            for i in range(n)
        ]

    if name == "Soft Ping":
        # High C6, very short, fast decay — barely-there notification
        dur, freq, amp, decay = 0.5, 1047, 0.35, 9.0
        n = int(sr * dur)
        return [
            int(32767 * amp * math.exp(-i / sr * decay)
                * math.sin(2 * math.pi * freq * i / sr))
            for i in range(n)
        ]

    if name == "Wind Chime":
        # Three ascending notes staggered in time
        total = 1.1
        n = int(sr * total)
        buf = [0.0] * n
        for freq, start_s in ((659, 0.0), (784, 0.32), (1047, 0.62)):
            t0 = int(sr * start_s)
            note_len = int(sr * 0.5)
            for j in range(note_len):
                idx = t0 + j
                if idx >= n:
                    break
                env = 0.30 * math.exp(-j / sr * 5.0)
                buf[idx] += env * math.sin(2 * math.pi * freq * j / sr)
        return [int(32767 * max(-1.0, min(1.0, v))) for v in buf]

    # Fallback: Soft Bell
    return _generate_sound("Soft Bell")


def play_sound(name: str) -> None:
    """Generate and play the named sound non-blocking (best-effort)."""
    raw = _generate_sound(name)
    frames = [struct.pack("<h", max(-32767, min(32767, s))) for s in raw]

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_path = tmp.name
    with wave.open(tmp_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(b"".join(frames))
    tmp.close()

    def _play():
        for cmd in (["paplay", tmp_path], ["aplay", tmp_path], ["afplay", tmp_path]):
            try:
                subprocess.run(cmd, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
                break
            except FileNotFoundError:
                continue
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    threading.Thread(target=_play, daemon=True).start()


# ── Pixel icon grids (8×8) ────────────────────────────────────────────────────
_G_CLOSE = [
    "10000001",
    "01000010",
    "00100100",
    "00011000",
    "00011000",
    "00100100",
    "01000010",
    "10000001",
]
_G_PAUSE = [
    "01100110",
    "01100110",
    "01100110",
    "01100110",
    "01100110",
    "01100110",
    "01100110",
    "00000000",
]
_G_PLAY = [
    "10000000",
    "11000000",
    "11100000",
    "11110000",
    "11100000",
    "11000000",
    "10000000",
    "00000000",
]
_G_PIN_ON = [
    "00111100",
    "01111110",
    "01111110",
    "00111100",
    "00011000",
    "00011000",
    "00000000",
    "00000000",
]
_G_PIN_OFF = [
    "00111100",
    "01000010",
    "01000010",
    "00111100",
    "00011000",
    "00011000",
    "00000000",
    "00000000",
]
_G_ADD = [
    "00011000",
    "00011000",
    "00011000",
    "11111111",
    "00011000",
    "00011000",
    "00011000",
    "00000000",
]
_G_HOURGLASS = [
    "11111111",
    "01111110",
    "00111100",
    "00011000",
    "00111100",
    "01111110",
    "11111111",
    "00000000",
]
# Musical eighth note
_G_NOTE = [
    "00001111",
    "00001001",
    "00001001",
    "00001001",
    "11101001",
    "11101001",
    "01100000",
    "00000000",
]
# Diamond / color swatch
_G_SWATCH = [
    "00011000",
    "00111100",
    "01111110",
    "11111111",
    "01111110",
    "00111100",
    "00011000",
    "00000000",
]
# Simple gear / cog
_G_GEAR = [
    "00011000",
    "01111110",
    "11011011",
    "11100111",
    "11100111",
    "11011011",
    "01111110",
    "00011000",
]


def make_icon(grid: list, fg: str, bg: str, scale: int = 2) -> tk.PhotoImage:
    """Build a PhotoImage from a pixel grid. Must be called after Tk() exists."""
    h, w = len(grid), len(grid[0])
    rows = []
    for row_str in grid:
        row = [fg if ch == "1" else bg for ch in row_str]
        scaled_row: list = []
        for c in row:
            scaled_row.extend([c] * scale)
        for _ in range(scale):
            rows.append(scaled_row[:])
    img = tk.PhotoImage(width=w * scale, height=h * scale)
    img.put(rows)
    return img


# ── Helpers ───────────────────────────────────────────────────────────────────
def luminance(hex_color: str) -> float:
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255


def text_color(bg: str) -> str:
    return "#1a1a1a" if luminance(bg) > 0.55 else "#ffffff"


def darken(hex_color: str, factor: float = 0.18) -> str:
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    r, g, b = (int(v * (1 - factor)) for v in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def parse_duration(text: str):
    """'25'→1500 s  '5:30'→330 s  '1:00:00'→3600 s.  Returns None on error."""
    parts = text.strip().split(":")
    try:
        if len(parts) == 1:
            return int(parts[0]) * 60
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        pass
    return None


def format_time(seconds: int) -> str:
    s = max(0, seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


# ── Timer Tile ────────────────────────────────────────────────────────────────
class TimerTile:
    def __init__(self, root, color: str, total_seconds: int,
                 tile_id: int, on_close, x: int = 120, y: int = 120):
        self.root          = root
        self.color         = color
        self.total_seconds = total_seconds
        self.remaining     = total_seconds
        self.tile_id       = tile_id
        self.on_close      = on_close
        self.running       = True
        self.pinned        = False
        self.finished      = False
        self.sound         = _settings["default_sound"]
        self._drag_ox      = 0
        self._drag_oy      = 0
        self._colorable    = []

        # Icon image refs (prevent GC)
        self.icon_close   = None
        self.icon_pin_on  = None
        self.icon_pin_off = None
        self.icon_pause   = None
        self.icon_play    = None
        self.icon_note    = None
        self.icon_swatch  = None

        self._build(x, y)
        self._tick()

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build(self, x: int, y: int):
        tc     = text_color(self.color)
        btn_bg = darken(self.color)

        win = tk.Toplevel(self.root)
        win.title("")
        win.geometry(f"220x200+{x}+{y}")
        win.resizable(False, False)
        win.configure(bg=self.color)
        win.protocol("WM_DELETE_WINDOW", self._close)

        try:
            win.wm_attributes("-type", "utility")
        except tk.TclError:
            pass

        self.win = win
        self._colorable.append(win)

        # Top bar ──────────────────────────────────────────────────────────────
        top = tk.Frame(win, bg=self.color)
        top.pack(fill="x", padx=8, pady=(8, 0))
        self._colorable.append(top)

        self.lbl_name = tk.Label(
            top, text=f"Timer {self.tile_id}",
            bg=self.color, fg=tc,
            font=("Helvetica", 10, "bold"), cursor="fleur",
        )
        self.lbl_name.pack(side="left")
        self._colorable.append(self.lbl_name)

        # Right side of top bar: close · pin · note (right-to-left packing)
        self.btn_close = tk.Button(
            top, text="", compound=tk.LEFT,
            bg=self.color, fg=tc,
            relief="flat", cursor="hand2",
            command=self._close, borderwidth=0, padx=3, pady=2,
        )
        self.btn_close.pack(side="right")
        self._colorable.append(self.btn_close)

        self.btn_pin = tk.Button(
            top, text="", compound=tk.LEFT,
            bg=self.color, fg=tc,
            relief="flat", cursor="hand2",
            command=self._toggle_pin, borderwidth=0, padx=3, pady=2,
        )
        self.btn_pin.pack(side="right")
        self._colorable.append(self.btn_pin)

        self.btn_sound = tk.Button(
            top, text="", compound=tk.LEFT,
            bg=self.color, fg=tc,
            relief="flat", cursor="hand2",
            command=self._show_sound_menu, borderwidth=0, padx=3, pady=2,
        )
        self.btn_sound.pack(side="right")
        self._colorable.append(self.btn_sound)

        self.btn_color = tk.Button(
            top, text="", compound=tk.LEFT,
            bg=self.color, fg=tc,
            relief="flat", cursor="hand2",
            command=self._pick_color, borderwidth=0, padx=3, pady=2,
        )
        self.btn_color.pack(side="right")
        self._colorable.append(self.btn_color)

        # Time display ─────────────────────────────────────────────────────────
        self.time_var = tk.StringVar(value=format_time(self.remaining))
        self.lbl_time = tk.Label(
            win, textvariable=self.time_var,
            bg=self.color, fg=tc,
            font=("Helvetica", 44, "bold"), cursor="fleur",
        )
        self.lbl_time.pack(expand=True)
        self._colorable.append(self.lbl_time)

        # Bottom bar ───────────────────────────────────────────────────────────
        bot = tk.Frame(win, bg=self.color)
        bot.pack(fill="x", padx=12, pady=(0, 12))
        self._colorable.append(bot)

        self.btn_pause = tk.Button(
            bot, text=" Pause", compound=tk.LEFT,
            bg=btn_bg, fg=tc,
            relief="flat", font=("Helvetica", 11, "bold"), cursor="hand2",
            command=self._toggle_pause, borderwidth=0, padx=10, pady=6,
        )
        self.btn_pause.pack(fill="x")

        # Drag targets ─────────────────────────────────────────────────────────
        for w in (win, self.lbl_time, self.lbl_name):
            w.bind("<Button-1>",  self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)

        self._rebuild_icons(tc, self.color)

    # ── Icon factory ──────────────────────────────────────────────────────────
    def _rebuild_icons(self, fg: str, tile_bg: str) -> None:
        btn_bg = darken(tile_bg)
        self.icon_close   = make_icon(_G_CLOSE,   fg, tile_bg)
        self.icon_pin_on  = make_icon(_G_PIN_ON,   fg, tile_bg)
        self.icon_pin_off = make_icon(_G_PIN_OFF,  fg, tile_bg)
        self.icon_pause   = make_icon(_G_PAUSE,    fg, btn_bg)
        self.icon_play    = make_icon(_G_PLAY,     fg, btn_bg)
        self.icon_note    = make_icon(_G_NOTE,     fg, tile_bg)
        self.icon_swatch  = make_icon(_G_SWATCH,   fg, tile_bg)

        self.btn_close.config(image=self.icon_close)
        self.btn_pin.config(
            image=self.icon_pin_on if self.pinned else self.icon_pin_off
        )
        self.btn_sound.config(image=self.icon_note)
        self.btn_color.config(image=self.icon_swatch)

        if self.finished:
            self.btn_pause.config(image=self.icon_play,  text=" Restart")
        elif self.running:
            self.btn_pause.config(image=self.icon_pause, text=" Pause")
        else:
            self.btn_pause.config(image=self.icon_play,  text=" Resume")

    # ── Sound menu ────────────────────────────────────────────────────────────
    def _show_sound_menu(self):
        menu = tk.Menu(
            self.win, tearoff=0,
            bg="#2d2d4e", fg=PANEL_FG,
            activebackground=PANEL_ACC, activeforeground=PANEL_BG,
            font=("Helvetica", 10),
        )
        for sname in SOUND_NAMES:
            label = ("  " if sname != self.sound else "> ") + sname
            menu.add_command(
                label=label,
                command=lambda s=sname: self._set_sound(s),
            )
        btn = self.btn_sound
        try:
            menu.tk_popup(
                btn.winfo_rootx(),
                btn.winfo_rooty() + btn.winfo_height(),
                0,
            )
        finally:
            menu.grab_release()

    def _set_sound(self, name: str) -> None:
        self.sound = name

    # ── Color picker ──────────────────────────────────────────────────────────
    def _pick_color(self) -> None:
        _, hexcolor = colorchooser.askcolor(
            color=self.color,
            title=f"Timer {self.tile_id} — pick color",
            parent=self.root,
        )
        if hexcolor:
            self.color = hexcolor
            self._apply_color(self.color)

    # ── Drag ──────────────────────────────────────────────────────────────────
    def _drag_start(self, e):
        self._drag_ox = e.x_root - self.win.winfo_x()
        self._drag_oy = e.y_root - self.win.winfo_y()

    def _drag_move(self, e):
        self.win.geometry(f"+{e.x_root - self._drag_ox}+{e.y_root - self._drag_oy}")

    # ── Controls ──────────────────────────────────────────────────────────────
    def _toggle_pause(self):
        if self.finished:
            self.remaining = self.total_seconds
            self.finished  = False
            self.running   = True
            self.time_var.set(format_time(self.remaining))
            self._apply_color(self.color)
            return
        self.running = not self.running
        tc     = text_color(self.color)
        btn_bg = darken(self.color)
        if self.running:
            self.btn_pause.config(image=self.icon_pause, text=" Pause",
                                  bg=btn_bg, fg=tc)
        else:
            self.btn_pause.config(image=self.icon_play,  text=" Resume",
                                  bg=btn_bg, fg=tc)

    def _toggle_pin(self):
        self.pinned = not self.pinned
        self.win.wm_attributes("-topmost", self.pinned)
        self.btn_pin.config(
            image=self.icon_pin_on if self.pinned else self.icon_pin_off
        )

    def _close(self):
        self.running = False
        if self.win.winfo_exists():
            self.win.destroy()
        self.on_close(self.tile_id)

    # ── Tick ──────────────────────────────────────────────────────────────────
    def _tick(self):
        if not self.win.winfo_exists():
            return
        if self.running and self.remaining > 0:
            self.remaining -= 1
            self.time_var.set(format_time(self.remaining))
            if self.remaining == 0:
                self.finished = True
                self._on_finish()
        self.win.after(1000, self._tick)

    def _on_finish(self):
        self.running = False
        play_sound(self.sound)
        self._flash(8)

    # ── Color helpers ─────────────────────────────────────────────────────────
    def _flash(self, remaining: int):
        if not self.win.winfo_exists():
            return
        if remaining <= 0:
            self._apply_color(self.color)
            return
        alt = "#ffffff" if (remaining % 2 == 0) else "#ff4444"
        self._apply_color(alt)
        self.win.after(220, lambda: self._flash(remaining - 1))

    def _apply_color(self, color: str):
        tc = text_color(color)
        try:
            for w in self._colorable:
                try:
                    w.configure(bg=color)
                except tk.TclError:
                    pass
                try:
                    w.configure(fg=tc)
                except tk.TclError:
                    pass
            self.btn_pause.configure(bg=darken(color), fg=tc)
            self._rebuild_icons(tc, color)
        except tk.TclError:
            pass


# ── Settings dialog ───────────────────────────────────────────────────────────
class SettingsDialog:
    def __init__(self, parent):
        self._parent = parent
        dlg = tk.Toplevel(parent)
        dlg.title("Settings")
        dlg.configure(bg=PANEL_BG)
        dlg.resizable(False, False)
        dlg.grab_set()
        self._dlg = dlg

        tk.Label(
            dlg, text="Default finish sound",
            bg=PANEL_BG, fg=PANEL_FG, font=("Helvetica", 11, "bold"),
        ).pack(padx=20, pady=(14, 8))

        sep = tk.Frame(dlg, bg="#2d2d4e", height=1)
        sep.pack(fill="x", padx=20, pady=(0, 10))

        self._var = tk.StringVar(value=_settings["default_sound"])

        for name in SOUND_NAMES:
            row = tk.Frame(dlg, bg=PANEL_BG)
            row.pack(fill="x", padx=20, pady=2)

            tk.Radiobutton(
                row, text=name, variable=self._var, value=name,
                bg=PANEL_BG, fg=PANEL_FG, selectcolor="#2d2d4e",
                activebackground=PANEL_BG, activeforeground=PANEL_FG,
                font=("Helvetica", 10), cursor="hand2",
            ).pack(side="left")

            tk.Button(
                row, text="Preview",
                bg="#2d2d4e", fg=PANEL_FG,
                relief="flat", font=("Helvetica", 9), cursor="hand2",
                command=lambda n=name: play_sound(n),
                padx=8, pady=2,
            ).pack(side="right")

        sep2 = tk.Frame(dlg, bg="#2d2d4e", height=1)
        sep2.pack(fill="x", padx=20, pady=(10, 0))

        tk.Button(
            dlg, text="Save & Close",
            bg=PANEL_ACC, fg=PANEL_BG,
            relief="flat", font=("Helvetica", 10, "bold"), cursor="hand2",
            command=self._save, padx=16, pady=6,
        ).pack(padx=20, pady=12)

        dlg.geometry(
            f"+{parent.winfo_x() + parent.winfo_width() + 6}"
            f"+{parent.winfo_y()}"
        )

    def _save(self):
        _settings["default_sound"] = self._var.get()
        self._dlg.destroy()


# ── Control Panel ─────────────────────────────────────────────────────────────
class ControlPanel:
    def __init__(self):
        self.root          = tk.Tk()
        self.root.title("Tiny Timer")
        self.root.resizable(False, False)
        self.root.configure(bg=PANEL_BG)
        self.tiles         = {}
        self._color_idx    = 0
        self._tile_counter = 0
        self._icon_hglass  = None
        self._icon_add     = None
        self._icon_gear    = None
        self._build_ui()

    def _build_ui(self):
        self._icon_hglass = make_icon(_G_HOURGLASS, PANEL_FG,  PANEL_BG,  scale=2)
        self._icon_add    = make_icon(_G_ADD,        PANEL_BG,  PANEL_ACC, scale=2)
        self._icon_gear   = make_icon(_G_GEAR,       PANEL_FG,  PANEL_BG,  scale=2)

        tk.Label(
            self.root,
            image=self._icon_hglass, text="  Tiny Timer", compound=tk.LEFT,
            bg=PANEL_BG, fg=PANEL_FG, font=("Helvetica", 13, "bold"),
        ).pack(pady=(12, 6))

        tk.Button(
            self.root,
            image=self._icon_add, text="  Add Timer", compound=tk.LEFT,
            bg=PANEL_ACC, fg=PANEL_BG,
            relief="flat", font=("Helvetica", 11, "bold"), cursor="hand2",
            command=self._add_tile, padx=14, pady=8,
        ).pack(padx=20, pady=(0, 6))

        tk.Button(
            self.root,
            image=self._icon_gear, text="  Settings", compound=tk.LEFT,
            bg=PANEL_BG, fg=PANEL_FG,
            relief="flat", font=("Helvetica", 9), cursor="hand2",
            command=self._open_settings, padx=14, pady=4,
        ).pack(padx=20, pady=(0, 12))

        self.root.geometry("200x125")

    def _open_settings(self):
        SettingsDialog(self.root)

    # ── Add tile ──────────────────────────────────────────────────────────────
    def _add_tile(self):
        seconds = self._ask_duration()
        if not seconds:
            return

        self._tile_counter += 1
        color = TILE_COLORS[self._color_idx % len(TILE_COLORS)]
        self._color_idx += 1

        offset = (self._tile_counter - 1) % 8 * 28
        rx = self.root.winfo_x()
        ry = self.root.winfo_y() + self.root.winfo_height() + 10

        tile = TimerTile(
            self.root, color, seconds,
            self._tile_counter, self._on_tile_close,
            x=rx + offset, y=ry + offset,
        )
        self.tiles[self._tile_counter] = tile

    # ── Duration dialog ───────────────────────────────────────────────────────
    def _ask_duration(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("New Timer")
        dlg.configure(bg=PANEL_BG)
        dlg.resizable(False, False)
        dlg.grab_set()

        result = [None]

        tk.Label(
            dlg, text="Duration  (e.g.  25  \u00b7  5:30  \u00b7  1:30:00)",
            bg=PANEL_BG, fg=PANEL_FG, font=("Helvetica", 10),
        ).pack(padx=18, pady=(12, 4))

        entry = tk.Entry(
            dlg, font=("Helvetica", 18), width=10, justify="center",
            bg="#2d2d4e", fg="#ffffff", insertbackground="white", relief="flat",
        )
        entry.pack(padx=18, pady=(0, 6))
        entry.insert(0, "25")
        entry.select_range(0, "end")
        entry.focus_set()

        err = tk.Label(dlg, text="", bg=PANEL_BG, fg="#ff6b6b",
                       font=("Helvetica", 9))
        err.pack()

        def submit(*_):
            secs = parse_duration(entry.get())
            if secs and secs > 0:
                result[0] = secs
                dlg.destroy()
            else:
                err.config(text="Invalid format \u2014 try: 25  or  5:30")

        entry.bind("<Return>", submit)

        tk.Button(
            dlg, text="Start",
            bg=PANEL_ACC, fg=PANEL_BG,
            relief="flat", font=("Helvetica", 10, "bold"), cursor="hand2",
            command=submit, padx=16, pady=6,
        ).pack(padx=18, pady=(4, 14))

        dlg.geometry(f"+{self.root.winfo_x() + 10}+{self.root.winfo_y() + 130}")
        self.root.wait_window(dlg)
        return result[0]

    def _on_tile_close(self, tile_id: int):
        self.tiles.pop(tile_id, None)

    def run(self):
        self.root.mainloop()


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ControlPanel().run()
