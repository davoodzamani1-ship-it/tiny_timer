#!/usr/bin/env python3
"""Tiny Timer — multiple floating timer tiles."""

import math
import os
import struct
import subprocess
import tempfile
import threading
import tkinter as tk
import tkinter.font as tkfont
import wave

try:
    from PIL import Image, ImageDraw, ImageTk
except ImportError:
    raise SystemExit("Pillow is required:  pip install pillow")

try:
    _RESAMPLE = Image.Resampling.LANCZOS   # Pillow >= 9.1
except AttributeError:
    _RESAMPLE = Image.LANCZOS              # Pillow < 9.1


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

# macOS system color palette — used in the per-tile color swatch picker
SWATCH_COLORS = [
    "#FF3B30", "#FF9500", "#FFCC00", "#34C759",  # red, orange, yellow, green
    "#00C7BE", "#32ADE6", "#007AFF", "#5856D6",  # teal, cyan, blue, indigo
    "#BF5AF2", "#FF375F", "#A2845E", "#8E8E93",  # purple, pink, brown, gray
    "#FF6B35", "#30D158", "#40C8E0", "#3A3A3C",  # warm-orange, lime, sky, dark
]

PANEL_BG  = "#16213e"
PANEL_FG  = "#eaeaea"
PANEL_ACC = "#4ECDC4"

# ── Font globals (resolved after Tk() init) ───────────────────────────────────
_FONT_UI   = "Helvetica"
_FONT_MONO = "Courier"

# ── Global app settings ───────────────────────────────────────────────────────
_settings = {"default_sound": "Wind Chime"}

# ── Sound definitions ─────────────────────────────────────────────────────────
SOUND_NAMES = [
    "Soft Bell", "Triple Bell",
    "Gentle Chime", "Gentle Chime ×2",
    "Marimba", "Soft Ping",
    "Wind Chime", "Wind Chime ×2",
]


def _sound_repeat(base: list, count: int, gap_ms: int = 340) -> list:
    gap = [0] * int(44100 * gap_ms / 1000)
    out = []
    for i in range(count):
        if i:
            out.extend(gap)
        out.extend(base)
    return out


def _generate_sound(name: str) -> list:
    sr = 44100
    if name == "Triple Bell":
        return _sound_repeat(_generate_sound("Soft Bell"), 3, gap_ms=300)
    if name == "Gentle Chime ×2":
        return _sound_repeat(_generate_sound("Gentle Chime"), 2, gap_ms=380)
    if name == "Wind Chime ×2":
        return _sound_repeat(_generate_sound("Wind Chime"), 2, gap_ms=500)
    if name == "Soft Bell":
        dur, freq, amp, decay = 1.2, 523, 0.50, 3.5
        n = int(sr * dur)
        return [int(32767 * amp * math.exp(-i / sr * decay)
                    * math.sin(2 * math.pi * freq * i / sr)) for i in range(n)]
    if name == "Gentle Chime":
        dur, f1, f2, amp, decay = 0.9, 523, 784, 0.40, 4.0
        n = int(sr * dur)
        return [int(32767 * amp * math.exp(-i / sr * decay)
                    * (0.65 * math.sin(2 * math.pi * f1 * i / sr)
                       + 0.35 * math.sin(2 * math.pi * f2 * i / sr))) for i in range(n)]
    if name == "Marimba":
        dur, freq, amp, decay = 0.7, 440, 0.45, 6.0
        n = int(sr * dur)
        return [int(32767 * amp * math.exp(-i / sr * decay)
                    * (0.60 * math.sin(2 * math.pi * freq * i / sr)
                       + 0.30 * math.sin(2 * math.pi * 2 * freq * i / sr)
                       + 0.10 * math.sin(2 * math.pi * 3 * freq * i / sr))) for i in range(n)]
    if name == "Soft Ping":
        dur, freq, amp, decay = 0.5, 1047, 0.35, 9.0
        n = int(sr * dur)
        return [int(32767 * amp * math.exp(-i / sr * decay)
                    * math.sin(2 * math.pi * freq * i / sr)) for i in range(n)]
    if name == "Wind Chime":
        total, n = 1.1, int(44100 * 1.1)
        buf = [0.0] * n
        for freq, start_s in ((659, 0.0), (784, 0.32), (1047, 0.62)):
            t0 = int(sr * start_s)
            for j in range(int(sr * 0.5)):
                idx = t0 + j
                if idx >= n:
                    break
                buf[idx] += 0.30 * math.exp(-j / sr * 5.0) * math.sin(2 * math.pi * freq * j / sr)
        return [int(32767 * max(-1.0, min(1.0, v))) for v in buf]
    return _generate_sound("Soft Bell")


def play_sound(name: str) -> None:
    raw    = _generate_sound(name)
    frames = [struct.pack("<h", max(-32767, min(32767, s))) for s in raw]
    tmp    = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_path = tmp.name
    with wave.open(tmp_path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(44100)
        w.writeframes(b"".join(frames))
    tmp.close()

    def _play():
        for cmd in (["paplay", tmp_path], ["aplay", tmp_path], ["afplay", tmp_path]):
            try:
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                break
            except FileNotFoundError:
                continue
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    threading.Thread(target=_play, daemon=True).start()


# ── Icon drawing helpers ───────────────────────────────────────────────────────
def _rl(d, x0, y0, x1, y1, fg, w):
    """Line with round caps — simulates vector stroke ends."""
    d.line([(x0, y0), (x1, y1)], fill=fg, width=w)
    r = w // 2
    d.ellipse([x0 - r, y0 - r, x0 + r, y0 + r], fill=fg)
    d.ellipse([x1 - r, y1 - r, x1 + r, y1 + r], fill=fg)


def _rrect(d, x0, y0, x1, y1, r, fg):
    """Filled rounded rectangle without requiring Pillow 8.2."""
    d.rectangle([x0 + r, y0, x1 - r, y1], fill=fg)
    d.rectangle([x0, y0 + r, x1, y1 - r], fill=fg)
    for cx, cy in ((x0 + r, y0 + r), (x1 - r, y0 + r),
                   (x0 + r, y1 - r), (x1 - r, y1 - r)):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fg)


# ── Icon drawing functions (operate on 4× canvas) ─────────────────────────────
def _di_close(d, S, fg):
    m = int(S * 0.22)
    w = max(4, int(S * 0.068))
    _rl(d, m, m, S - m, S - m, fg, w)
    _rl(d, S - m, m, m, S - m, fg, w)


def _di_pause(d, S, fg):
    bw = int(S * 0.165)
    r  = max(2, int(S * 0.05))
    g  = int(S * 0.09)
    cx = S // 2
    y0, y1 = int(S * 0.17), int(S * 0.83)
    _rrect(d, cx - g - bw, y0, cx - g,    y1, r, fg)
    _rrect(d, cx + g,      y0, cx + g + bw, y1, r, fg)


def _di_play(d, S, fg):
    m  = int(S * 0.16)
    xr = int(S * 0.82)
    d.polygon([(m, m), (m, S - m), (xr, S // 2)], fill=fg)


def _di_pin_on(d, S, fg):
    r  = int(S * 0.28)
    cx, cy = S // 2, int(S * 0.38)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fg)
    d.polygon([
        (int(cx - r * 0.72), int(cy + r * 0.45)),
        (int(cx + r * 0.72), int(cy + r * 0.45)),
        (cx, int(S * 0.88)),
    ], fill=fg)
    r2 = int(r * 0.40)
    d.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], fill=(0, 0, 0, 0))


def _di_pin_off(d, S, fg):
    w  = max(3, int(S * 0.065))
    r  = int(S * 0.26)
    cx, cy = S // 2, int(S * 0.36)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=fg, width=w)
    tip = int(S * 0.86)
    _rl(d, int(cx - r * 0.76), int(cy + r * 0.52), cx, tip, fg, w)
    _rl(d, int(cx + r * 0.76), int(cy + r * 0.52), cx, tip, fg, w)


def _di_note(d, S, fg):
    w   = max(3, int(S * 0.065))
    sx  = int(S * 0.62)
    sy0 = int(S * 0.14)
    sy1 = int(S * 0.72)
    _rl(d, sx, sy0, sx, sy1, fg, w)
    _rl(d, sx, sy0, int(S * 0.87), int(S * 0.27), fg, w)
    r1, r2 = int(S * 0.18), int(S * 0.13)
    hx, hy = int(S * 0.40), int(S * 0.77)
    d.ellipse([hx - r1, hy - r2, hx + r1, hy + r2], fill=fg)


def _di_swatch(d, S, fg):
    m = int(S * 0.10)
    d.ellipse([m, m, S - m, S - m], fill=fg)


def _di_gear(d, S, fg):
    cx = cy = S / 2
    r_out, r_mid, r_in, r_hole = S * 0.42, S * 0.30, S * 0.19, S * 0.11
    pts = []
    for i in range(8):
        for frac, r in ((0.04, r_mid), (0.14, r_out), (0.36, r_out), (0.46, r_mid)):
            a = 2 * math.pi * (i + frac) / 8
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    d.polygon([(int(x), int(y)) for x, y in pts], fill=fg)
    ri = int(r_in)
    d.ellipse([int(cx) - ri, int(cy) - ri, int(cx) + ri, int(cy) + ri], fill=fg)
    rh = int(r_hole)
    d.ellipse([int(cx) - rh, int(cy) - rh, int(cx) + rh, int(cy) + rh], fill=(0, 0, 0, 0))


def _di_add(d, S, fg):
    w  = max(3, int(S * 0.08))
    m  = int(S * 0.18)
    cx = cy = S // 2
    _rl(d, cx, m, cx, S - m, fg, w)
    _rl(d, m, cy, S - m, cy, fg, w)


def _di_check(d, S, fg):
    w = max(3, int(S * 0.09))
    _rl(d, int(S*0.12), int(S*0.52), int(S*0.40), int(S*0.80), fg, w)
    _rl(d, int(S*0.40), int(S*0.80), int(S*0.88), int(S*0.18), fg, w)


def _di_hourglass(d, S, fg):
    m   = int(S * 0.12)
    mid = S // 2
    bh  = max(3, int(S * 0.06))
    d.polygon([(m, m),     (S - m, m),     (mid, mid)], fill=fg)
    d.polygon([(m, S - m), (S - m, S - m), (mid, mid)], fill=fg)
    d.rectangle([m, m,          S - m, m + bh], fill=fg)
    d.rectangle([m, S - m - bh, S - m, S - m ], fill=fg)


# ── Icon factory ──────────────────────────────────────────────────────────────
_icon_cache: dict = {}


def _hex_rgba(h: str) -> tuple:
    return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16), 255)


def make_icon(draw_fn, size: int, fg: str, bg: str = None) -> ImageTk.PhotoImage:
    """Render an anti-aliased icon at 4× scale, downscale with LANCZOS.
    Pass bg=None for a transparent background (ghost icon style)."""
    key = (draw_fn, size, fg, bg)
    hit = _icon_cache.get(key)
    if hit is not None:
        return hit

    S   = size * 4
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(img), S, _hex_rgba(fg))
    img = img.resize((size, size), _RESAMPLE)
    if bg is not None:
        bg_img = Image.new("RGBA", (size, size), _hex_rgba(bg))
        img    = Image.alpha_composite(bg_img, img)
    photo = ImageTk.PhotoImage(img)

    if len(_icon_cache) > 300:
        _icon_cache.clear()
    _icon_cache[key] = photo
    return photo


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
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


# ── Color swatch popup ────────────────────────────────────────────────────────
class ColorSwatchPopup:
    _SW   = 26   # swatch pixel size
    _GAP  = 3    # gap between swatches
    _COLS = 4

    def __init__(self, parent, anchor, callback):
        self._cb = callback

        popup = tk.Toplevel(parent)
        popup.overrideredirect(True)
        popup.configure(bg="#2a3052")        # thin border color
        popup.wm_attributes("-topmost", True)
        self._popup = popup

        inner = tk.Frame(popup, bg=PANEL_BG, padx=5, pady=5)
        inner.pack(padx=1, pady=1)

        SW, GAP = self._SW, self._GAP
        for i, color in enumerate(SWATCH_COLORS):
            r, c = divmod(i, self._COLS)
            f = tk.Frame(inner, bg=color, width=SW, height=SW, cursor="hand2")
            f.grid(row=r, column=c, padx=GAP // 2, pady=GAP // 2)
            f.bind("<Button-1>", lambda e, col=color: self._pick(col))
            f.bind("<Enter>", lambda e, col=color, w=f: w.configure(bg=darken(col, 0.15)))
            f.bind("<Leave>", lambda e, col=color, w=f: w.configure(bg=col))

        # Position just below the anchor widget
        popup.update_idletasks()
        px = anchor.winfo_rootx()
        py = anchor.winfo_rooty() + anchor.winfo_height() + 2
        popup.geometry(f"+{px}+{py}")

        popup.bind("<Escape>", lambda e: popup.destroy())
        popup.grab_set()
        popup.focus_set()

    def _pick(self, color: str):
        self._popup.grab_release()
        self._popup.destroy()
        self._cb(color)


# ── Timer Tile ────────────────────────────────────────────────────────────────
class TimerTile:
    _ICON_SIZE   = 20   # tile top-bar icon size
    _PAUSE_ICON  = 18   # pause button icon size

    def __init__(self, root, color: str, total_seconds: int,
                 tile_id: int, on_close, on_tick=None,
                 x: int = 120, y: int = 120):
        self.root          = root
        self.color         = color
        self.total_seconds = total_seconds
        self.remaining     = total_seconds
        self.tile_id       = tile_id
        self.on_close      = on_close
        self.on_tick       = on_tick
        self.running       = True
        self.pinned        = False
        self.finished      = False
        self.sound         = _settings["default_sound"]
        self._drag_ox      = 0
        self._drag_oy      = 0
        self._colorable    = []

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

        # Top bar ──────────────────────────────────────────────────────────
        top = tk.Frame(win, bg=self.color)
        top.pack(fill="x", padx=8, pady=(8, 0))
        self._colorable.append(top)

        self.lbl_name = tk.Label(
            top, text=f"Timer {self.tile_id}",
            bg=self.color, fg=tc,
            font=(_FONT_UI, 10), cursor="fleur",
        )
        self.lbl_name.pack(side="left")
        self._colorable.append(self.lbl_name)

        def _icon_btn(parent, cmd):
            b = tk.Button(
                parent, text="", compound=tk.LEFT,
                bg=self.color, fg=tc,
                relief="flat", cursor="hand2",
                command=cmd, borderwidth=0,
                highlightthickness=0, padx=3, pady=3,
            )
            self._colorable.append(b)
            return b

        self.btn_close = _icon_btn(top, self._close);           self.btn_close.pack(side="right")
        self.btn_pin   = _icon_btn(top, self._toggle_pin);      self.btn_pin.pack(side="right")
        self.btn_sound = _icon_btn(top, self._show_sound_menu); self.btn_sound.pack(side="right")
        self.btn_color = _icon_btn(top, self._pick_color);      self.btn_color.pack(side="right")

        # Time display ─────────────────────────────────────────────────────
        self.time_var = tk.StringVar(value=format_time(self.remaining))
        self.lbl_time = tk.Label(
            win, textvariable=self.time_var,
            bg=self.color, fg=tc,
            font=(_FONT_UI, self._time_font_size(self.remaining), "bold"),
            cursor="fleur",
        )
        self.lbl_time.pack(expand=True)
        self._colorable.append(self.lbl_time)

        # Pause / Resume button ────────────────────────────────────────────
        bot = tk.Frame(win, bg=self.color)
        bot.pack(fill="x", padx=12, pady=(0, 12))
        self._colorable.append(bot)

        self.btn_pause = tk.Button(
            bot, text=" Pause", compound=tk.LEFT,
            bg=btn_bg, fg=tc,
            relief="flat", font=(_FONT_UI, 10, "bold"), cursor="hand2",
            command=self._toggle_pause, borderwidth=0,
            highlightthickness=0, padx=10, pady=8,
        )
        self.btn_pause.pack(fill="x")

        for w in (win, self.lbl_time, self.lbl_name):
            w.bind("<Button-1>",  self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)

        self._rebuild_icons(tc, self.color)

    # ── Icon factory ──────────────────────────────────────────────────────────
    def _rebuild_icons(self, fg: str, tile_bg: str) -> None:
        sz     = self._ICON_SIZE
        psz    = self._PAUSE_ICON
        btn_bg = darken(tile_bg)
        # Subtle press feedback — just a slight darkening, no harsh flash
        abg      = darken(tile_bg, 0.10)
        pause_abg = darken(btn_bg, 0.10)

        # Ghost icons: no baked background — transparent areas show the button's own bg
        self.icon_close   = make_icon(_di_close,   sz,  fg)
        self.icon_pin_on  = make_icon(_di_pin_on,  sz,  fg)
        self.icon_pin_off = make_icon(_di_pin_off, sz,  fg)
        self.icon_pause   = make_icon(_di_pause,   psz, fg)
        self.icon_play    = make_icon(_di_play,    psz, fg)
        self.icon_note    = make_icon(_di_note,    sz,  fg)
        self.icon_swatch  = make_icon(_di_swatch,  sz,  fg)

        self.btn_close.config(image=self.icon_close,
                              activebackground=abg, activeforeground=fg)
        self.btn_pin.config(
            image=self.icon_pin_on if self.pinned else self.icon_pin_off,
            activebackground=abg, activeforeground=fg,
        )
        self.btn_sound.config(image=self.icon_note,
                              activebackground=abg, activeforeground=fg)
        self.btn_color.config(image=self.icon_swatch,
                              activebackground=abg, activeforeground=fg)

        if self.finished:
            self.btn_pause.config(image=self.icon_play,  text=" Restart",
                                  activebackground=pause_abg, activeforeground=fg)
        elif self.running:
            self.btn_pause.config(image=self.icon_pause, text=" Pause",
                                  activebackground=pause_abg, activeforeground=fg)
        else:
            self.btn_pause.config(image=self.icon_play,  text=" Resume",
                                  activebackground=pause_abg, activeforeground=fg)

    # ── Sound menu ────────────────────────────────────────────────────────────
    def _show_sound_menu(self):
        menu = tk.Menu(
            self.win, tearoff=0,
            bg="#2d2d4e", fg=PANEL_FG,
            activebackground=PANEL_ACC, activeforeground=PANEL_BG,
            font=(_FONT_UI, 10),
        )
        for sname in SOUND_NAMES:
            label = ("  " if sname != self.sound else "> ") + sname
            menu.add_command(label=label, command=lambda s=sname: self._set_sound(s))
        btn = self.btn_sound
        try:
            menu.tk_popup(btn.winfo_rootx(), btn.winfo_rooty() + btn.winfo_height(), 0)
        finally:
            menu.grab_release()

    def _set_sound(self, name: str) -> None:
        self.sound = name

    # ── Color picker ──────────────────────────────────────────────────────────
    def _pick_color(self) -> None:
        ColorSwatchPopup(self.win, self.btn_color, self._on_color_picked)

    def _on_color_picked(self, color: str) -> None:
        self.color = color
        self._apply_color(self.color)
        self._notify_tick()

    # ── Time display helpers ───────────────────────────────────────────────────
    @staticmethod
    def _time_font_size(seconds: int) -> int:
        return 32 if seconds >= 3600 else 44

    def _update_display(self, seconds: int) -> None:
        self.time_var.set(format_time(seconds))
        self.lbl_time.configure(font=(_FONT_UI, self._time_font_size(seconds), "bold"))

    # ── Drag ──────────────────────────────────────────────────────────────────
    def _drag_start(self, e):
        # Ignore clicks that originate from buttons — let the button handle them
        if isinstance(e.widget, tk.Button):
            return
        self._drag_ox = e.x_root - self.win.winfo_x()
        self._drag_oy = e.y_root - self.win.winfo_y()

    def _drag_move(self, e):
        if isinstance(e.widget, tk.Button):
            return
        self.win.geometry(f"+{e.x_root - self._drag_ox}+{e.y_root - self._drag_oy}")

    # ── Controls ──────────────────────────────────────────────────────────────
    def _toggle_pause(self):
        if self.finished:
            self.remaining = self.total_seconds
            self.finished  = False
            self.running   = True
            self._update_display(self.remaining)
            self._apply_color(self.color)
            self._notify_tick()
            return
        self.running = not self.running
        tc     = text_color(self.color)
        btn_bg = darken(self.color)
        abg    = darken(btn_bg, 0.10)
        if self.running:
            self.btn_pause.config(image=self.icon_pause, text=" Pause",
                                  bg=btn_bg, fg=tc, activebackground=abg)
        else:
            self.btn_pause.config(image=self.icon_play,  text=" Resume",
                                  bg=btn_bg, fg=tc, activebackground=abg)
        self._notify_tick()

    def _toggle_pin(self):
        self.pinned = not self.pinned
        self.win.wm_attributes("-topmost", self.pinned)
        self.btn_pin.config(image=self.icon_pin_on if self.pinned else self.icon_pin_off)

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
            self._update_display(self.remaining)
            if self.remaining == 0:
                self.finished = True
                self._on_finish()
        self._notify_tick()
        self.win.after(1000, self._tick)

    def _on_finish(self):
        self.running = False
        play_sound(self.sound)
        self._flash(8)

    def _notify_tick(self):
        if self.on_tick:
            self.on_tick(self.tile_id, self.remaining, self.running,
                         self.finished, self.color)

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
                try:    w.configure(bg=color)
                except tk.TclError: pass
                try:    w.configure(fg=tc)
                except tk.TclError: pass
            self.btn_pause.configure(bg=darken(color), fg=tc)
            self._rebuild_icons(tc, color)
        except tk.TclError:
            pass


# ── Settings dialog ───────────────────────────────────────────────────────────
class SettingsDialog:
    def __init__(self, parent):
        dlg = tk.Toplevel(parent)
        dlg.title("Settings")
        dlg.configure(bg=PANEL_BG)
        dlg.resizable(False, False)
        dlg.grab_set()
        self._dlg = dlg

        tk.Label(dlg, text="Default finish sound",
                 bg=PANEL_BG, fg=PANEL_FG,
                 font=(_FONT_UI, 11, "bold")).pack(padx=20, pady=(14, 8))
        tk.Frame(dlg, bg="#2d2d4e", height=1).pack(fill="x", padx=20, pady=(0, 10))

        self._var = tk.StringVar(value=_settings["default_sound"])
        for name in SOUND_NAMES:
            row = tk.Frame(dlg, bg=PANEL_BG)
            row.pack(fill="x", padx=20, pady=2)
            tk.Radiobutton(
                row, text=name, variable=self._var, value=name,
                bg=PANEL_BG, fg=PANEL_FG, selectcolor="#2d2d4e",
                activebackground=PANEL_BG, activeforeground=PANEL_FG,
                font=(_FONT_UI, 10), cursor="hand2",
            ).pack(side="left")
            tk.Button(
                row, text="Preview", bg="#2d2d4e", fg=PANEL_FG,
                relief="flat", font=(_FONT_UI, 9), cursor="hand2",
                command=lambda n=name: play_sound(n), padx=8, pady=2,
                activebackground="#3d3d5e", activeforeground=PANEL_FG,
            ).pack(side="right")

        tk.Frame(dlg, bg="#2d2d4e", height=1).pack(fill="x", padx=20, pady=(10, 0))
        tk.Button(
            dlg, text="Save & Close", bg=PANEL_ACC, fg=PANEL_BG,
            relief="flat", font=(_FONT_UI, 10, "bold"), cursor="hand2",
            command=self._save, padx=16, pady=6,
            activebackground=darken(PANEL_ACC, 0.15), activeforeground=PANEL_BG,
        ).pack(padx=20, pady=12)

        dlg.geometry(
            f"+{parent.winfo_x() + parent.winfo_width() + 6}+{parent.winfo_y()}"
        )

    def _save(self):
        _settings["default_sound"] = self._var.get()
        self._dlg.destroy()


# ── Control Panel ─────────────────────────────────────────────────────────────
class ControlPanel:
    _ROW_ICON = 16   # row icon size
    _HDR_ICON = 18   # header icon size

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Tiny Timer")
        self.root.resizable(False, False)
        self.root.configure(bg=PANEL_BG)

        self._init_fonts()

        self.tiles         = {}
        self._color_idx    = 0
        self._tile_counter = 0

        self._icon_hglass    = None
        self._icon_add       = None
        self._icon_gear      = None
        self._row_icon_pause = None
        self._row_icon_play  = None
        self._row_icon_close = None

        self._list_sep   = None
        self._list_frame = None
        self._rows       = {}

        self._build_ui()

    def _init_fonts(self):
        global _FONT_UI, _FONT_MONO
        # Case-insensitive lookup: lowercase -> actual name as returned by tkfont
        avail = {f.lower(): f for f in tkfont.families()}

        def _pick(candidates, default):
            for c in candidates:
                hit = avail.get(c.lower())
                if hit:
                    return hit
            return default

        _FONT_UI   = _pick([
            "Inter", "SF Pro Display", "Roboto", "Noto Sans", "Open Sans",
            "Source Sans Pro", "Lato", "Ubuntu", "Cantarell",
            "texgyreheros", "nimbus sans l", "Helvetica",
        ], "Helvetica")
        _FONT_MONO = _pick([
            "JetBrains Mono", "Fira Code", "Fira Mono", "Roboto Mono",
            "IBM Plex Mono", "Source Code Pro", "Ubuntu Mono",
            "Noto Mono", "DejaVu Sans Mono", "Liberation Mono",
            "nimbus mono l", "Courier New",
        ], "Courier")

    def _build_ui(self):
        sz  = self._HDR_ICON
        rsz = self._ROW_ICON

        self._icon_hglass    = make_icon(_di_hourglass, sz,  PANEL_FG,  PANEL_BG)
        self._icon_add       = make_icon(_di_add,       sz,  PANEL_BG,  PANEL_ACC)
        self._icon_gear      = make_icon(_di_gear,      sz,  "#8899bb", PANEL_BG)
        # Row icons: ghost style — transparent bg, muted fg
        self._row_icon_pause = make_icon(_di_pause, rsz, "#8899bb")
        self._row_icon_play  = make_icon(_di_play,  rsz, "#8899bb")
        self._row_icon_close = make_icon(_di_close, rsz, "#555577")

        # ── Header: title left, gear right ────────────────────────────────
        hdr = tk.Frame(self.root, bg=PANEL_BG)
        hdr.pack(fill="x", padx=14, pady=(14, 8))

        tk.Label(
            hdr,
            image=self._icon_hglass, text="  Tiny Timer", compound=tk.LEFT,
            bg=PANEL_BG, fg=PANEL_FG, font=(_FONT_UI, 12, "bold"),
        ).pack(side="left")

        tk.Button(
            hdr, image=self._icon_gear, text="",
            bg=PANEL_BG, relief="flat", cursor="hand2",
            command=self._open_settings,
            borderwidth=0, highlightthickness=0, padx=2, pady=2,
            activebackground="#1e2845",
        ).pack(side="right")

        # ── Add Timer — full width ─────────────────────────────────────────
        tk.Button(
            self.root,
            image=self._icon_add, text="  Add Timer", compound=tk.LEFT,
            bg=PANEL_ACC, fg=PANEL_BG,
            relief="flat", font=(_FONT_UI, 10, "bold"), cursor="hand2",
            command=self._add_tile, padx=0, pady=9,
            activebackground=darken(PANEL_ACC, 0.12), activeforeground=PANEL_BG,
            highlightthickness=0, borderwidth=0,
        ).pack(fill="x", padx=14, pady=(0, 12))

        self._list_sep = tk.Frame(self.root, bg="#252d4a", height=1)
        self._list_sep.pack(fill="x")
        self._list_sep.pack_forget()

        self._list_frame = tk.Frame(self.root, bg=PANEL_BG)
        self._list_frame.pack(fill="x")
        self._list_frame.pack_forget()

        self.root.geometry("210x86")

    def _open_settings(self):
        SettingsDialog(self.root)

    # ── Add tile ──────────────────────────────────────────────────────────────
    def _add_tile(self):
        seconds = self._ask_duration()
        if not seconds:
            return
        self._tile_counter += 1
        color  = TILE_COLORS[self._color_idx % len(TILE_COLORS)]
        self._color_idx += 1
        offset = (self._tile_counter - 1) % 8 * 28
        rx, ry = self.root.winfo_x(), self.root.winfo_y() + self.root.winfo_height() + 10
        tile = TimerTile(
            self.root, color, seconds,
            self._tile_counter, self._on_tile_close,
            on_tick=self._on_tile_tick,
            x=rx + offset, y=ry + offset,
        )
        self.tiles[self._tile_counter] = tile
        self._add_list_row(self._tile_counter, color, f"Timer {self._tile_counter}")

    # ── Timer list ────────────────────────────────────────────────────────────
    def _add_list_row(self, tile_id: int, color: str, name: str):
        row = tk.Frame(self._list_frame, bg=PANEL_BG)
        row.pack(fill="x", padx=10, pady=2)

        dot = tk.Frame(row, bg=color, width=10, height=10)
        dot.pack_propagate(False)
        dot.pack(side="left", padx=(0, 8), pady=4)

        name_lbl = tk.Label(row, text=name, bg=PANEL_BG, fg=PANEL_FG,
                            font=(_FONT_UI, 9), anchor="w", cursor="xterm")
        name_lbl.pack(side="left")
        name_lbl.bind("<Double-Button-1>",
                      lambda e, tid=tile_id: self._start_rename(tid))

        close_btn = tk.Button(
            row, image=self._row_icon_close, text="",
            bg=PANEL_BG, relief="flat", cursor="hand2",
            command=lambda tid=tile_id: self._row_close(tid),
            borderwidth=0, highlightthickness=0, padx=2,
            activebackground="#1e2845",
        )
        close_btn.pack(side="right", padx=(0, 2))

        pause_btn = tk.Button(
            row, image=self._row_icon_pause, text="",
            bg=PANEL_BG, relief="flat", cursor="hand2",
            command=lambda tid=tile_id: self._row_toggle_pause(tid),
            borderwidth=0, highlightthickness=0, padx=2,
            activebackground="#1e2845",
        )
        pause_btn.pack(side="right", padx=2)

        time_lbl = tk.Label(
            row, text=format_time(self.tiles[tile_id].remaining),
            bg=PANEL_BG, fg=PANEL_ACC,
            font=(_FONT_MONO, 9), width=8, anchor="e",
        )
        time_lbl.pack(side="right", padx=(2, 4))

        self._rows[tile_id] = {
            "frame": row, "dot": dot,
            "time_lbl": time_lbl, "pause_btn": pause_btn,
            "name_lbl": name_lbl,
        }
        self._refresh_list_visibility()

    def _start_rename(self, tile_id: int):
        row_data = self._rows.get(tile_id)
        if not row_data:
            return
        name_lbl = row_data["name_lbl"]
        # If an edit is already active on this row, do nothing
        if row_data.get("_editing"):
            return
        row_data["_editing"] = True
        name_lbl.pack_forget()
        row_data["time_lbl"].pack_forget()   # reclaim space for the entry

        # Container styled as the input box — entry + checkmark live inside it
        box = tk.Frame(
            row_data["frame"],
            bg="#1e2845",
            highlightthickness=1,
            highlightbackground="#2d3555",
            highlightcolor=PANEL_ACC,
        )
        box.pack(side="left")

        entry = tk.Entry(
            box,
            font=(_FONT_UI, 9), width=9,
            bg="#1e2845", fg=PANEL_FG,
            insertbackground=PANEL_FG,
            relief="flat", bd=0,
            highlightthickness=0,
        )
        entry.insert(0, name_lbl.cget("text"))
        entry.select_range(0, "end")
        entry.pack(side="left", padx=(4, 0), pady=1)

        check_icon = make_icon(_di_check, 12, PANEL_ACC)
        check_btn = tk.Button(
            box, image=check_icon, text="",
            bg="#1e2845", relief="flat", cursor="hand2",
            borderwidth=0, highlightthickness=0,
            padx=3, pady=1,
            activebackground="#2a3a5e",
        )
        check_btn._icon = check_icon   # prevent GC
        check_btn.pack(side="left", padx=(2, 3))

        edit_widgets = [box]
        _done = [False]

        def confirm(*_):
            if _done[0]:
                return
            _done[0] = True
            self._confirm_rename(tile_id, entry.get(), edit_widgets)

        entry.bind("<Return>", confirm)
        entry.bind("<FocusOut>", confirm)
        entry.bind("<Escape>", lambda e: confirm())
        check_btn.config(command=confirm)
        entry.focus_set()

    def _confirm_rename(self, tile_id: int, new_name: str, edit_widgets: list):
        row_data = self._rows.get(tile_id)
        if not row_data:
            return
        new_name = new_name.strip() or row_data["name_lbl"].cget("text")
        for w in edit_widgets:
            try:
                w.destroy()
            except tk.TclError:
                pass
        row_data["name_lbl"].config(text=new_name)
        row_data["name_lbl"].pack(side="left")
        row_data["time_lbl"].pack(side="right", padx=(2, 4))
        row_data["_editing"] = False
        # Sync to the tile's own name label
        tile = self.tiles.get(tile_id)
        if tile and tile.win.winfo_exists():
            tile.lbl_name.config(text=new_name)

    def _on_tile_tick(self, tile_id: int, remaining: int,
                      running: bool, finished: bool, color: str):
        row_data = self._rows.get(tile_id)
        if not row_data:
            return
        row_data["time_lbl"].config(text=format_time(remaining))
        row_data["dot"].config(bg=color)
        row_data["pause_btn"].config(
            image=self._row_icon_pause if running else self._row_icon_play
        )

    def _row_toggle_pause(self, tile_id: int):
        tile = self.tiles.get(tile_id)
        if tile:
            tile._toggle_pause()

    def _row_close(self, tile_id: int):
        tile = self.tiles.get(tile_id)
        if tile:
            tile._close()

    def _refresh_list_visibility(self):
        if self._rows:
            self._list_sep.pack(fill="x")
            self._list_frame.pack(fill="x", pady=(0, 8))
        else:
            self._list_sep.pack_forget()
            self._list_frame.pack_forget()
        self.root.update_idletasks()
        self.root.geometry(f"210x{self.root.winfo_reqheight()}")

    def _on_tile_close(self, tile_id: int):
        self.tiles.pop(tile_id, None)
        row_data = self._rows.pop(tile_id, None)
        if row_data:
            row_data["frame"].destroy()
        self._refresh_list_visibility()

    # ── Duration dialog ───────────────────────────────────────────────────────
    def _ask_duration(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("New Timer")
        dlg.configure(bg=PANEL_BG)
        dlg.resizable(False, False)
        dlg.grab_set()

        result = [None]

        tk.Label(dlg, text="Duration  (e.g.  25  \u00b7  5:30  \u00b7  1:30:00)",
                 bg=PANEL_BG, fg=PANEL_FG, font=(_FONT_UI, 10)).pack(padx=18, pady=(12, 4))

        entry = tk.Entry(
            dlg, font=(_FONT_MONO, 18), width=10, justify="center",
            bg="#2d2d4e", fg="#ffffff", insertbackground="white", relief="flat",
        )
        entry.pack(padx=18, pady=(0, 6))
        entry.insert(0, "25")
        entry.select_range(0, "end")
        entry.focus_set()

        err = tk.Label(dlg, text="", bg=PANEL_BG, fg="#ff6b6b", font=(_FONT_UI, 9))
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
            dlg, text="Start", bg=PANEL_ACC, fg=PANEL_BG,
            relief="flat", font=(_FONT_UI, 10, "bold"), cursor="hand2",
            command=submit, padx=16, pady=6,
            activebackground=darken(PANEL_ACC, 0.15), activeforeground=PANEL_BG,
        ).pack(padx=18, pady=(4, 14))

        dlg.geometry(f"+{self.root.winfo_x() + 10}+{self.root.winfo_y() + 130}")
        self.root.wait_window(dlg)
        return result[0]

    def run(self):
        self.root.mainloop()


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ControlPanel().run()
