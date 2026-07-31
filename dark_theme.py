#!/usr/bin/env python3
"""
Midnight/Blue Dark Theme for the Atmos Binaural Converter GUI.

Centralizes the color palette and applies a consistent dark ttk 'clam'
style set (frames, labels, notebooks, buttons, comboboxes, progressbars,
scales, scrollbars, listboxes) plus a dark Windows title bar.

Any module can import the palette for custom widgets:
    from dark_theme import PALETTE, apply_dark_theme
"""

import sys
import ctypes
import tkinter as tk
from tkinter import ttk

# ---------------------------------------------------------------- palette
PALETTE = {
    # surfaces
    "bg":            "#0f1420",   # window background (midnight)
    "surface":       "#1a2233",   # raised cards / frame bodies
    "surface2":      "#222c42",   # inputs, buttons
    "surface3":      "#2b3750",   # hover / selected
    "canvas_bg":     "#0a0e17",   # canvas / listbox background (deepest)
    "border":        "#33415e",   # subtle borders
    "border_hi":     "#46597f",   # bright borders
    # text
    "text":          "#e8edf6",   # primary text
    "muted":         "#93a0b8",   # secondary text
    "faint":         "#5b6a85",   # tertiary / placeholders
    # accents
    "accent":        "#4f8cff",   # primary blue
    "accent_hi":     "#7db0ff",   # accent hover
    "accent_dark":   "#2f5fd0",   # accent pressed
    "ok":            "#3ddc84",   # success green
    "warn":          "#ffb454",   # warning amber
    "err":           "#ff6b6b",   # error red
    # speaker colors
    "front":         "#4f8cff",   # front speakers
    "rear":          "#ff6b6b",   # rear speakers
    "side":          "#3ddc84",   # side speakers
    "lfe":           "#b06bff",   # subwoofer
    "head":          "#e8edf6",   # listener head
}


def apply_dark_theme(root: tk.Tk) -> None:
    """
    Apply the midnight/blue theme to a Tk root and all future ttk widgets.

    Call once after creating the root (or inside setup_styles).
    """
    P = PALETTE
    style = ttk.Style(root)
    style.theme_use("clam")

    # ---- base ----------------------------------------------------------
    style.configure(".", background=P["bg"], foreground=P["text"],
                    fieldbackground=P["surface2"], bordercolor=P["border"],
                    lightcolor=P["surface3"], darkcolor=P["border"],
                    troughcolor=P["surface"], selectbackground=P["accent"],
                    selectforeground="#ffffff", focuscolor=P["accent"])

    # ---- frames & labels ----------------------------------------------
    style.configure("TFrame", background=P["bg"])
    style.configure("TLabel", background=P["bg"], foreground=P["text"])
    style.configure("TLabelframe", background=P["bg"], bordercolor=P["border"],
                    relief="solid", borderwidth=1)
    style.configure("TLabelframe.Label", background=P["bg"],
                    foreground=P["muted"], font=("Segoe UI", 9, "bold"))
    style.configure("TNotebook", background=P["bg"], borderwidth=0)
    style.configure("TNotebook.Tab", background=P["surface2"],
                    foreground=P["muted"], padding=(16, 8), borderwidth=1,
                    bordercolor=P["border"])
    style.map("TNotebook.Tab",
              background=[("selected", P["surface"])],
              foreground=[("selected", P["accent_hi"])],
              bordercolor=[("selected", P["accent"])])

    # ---- buttons -------------------------------------------------------
    style.configure("TButton", background=P["surface2"], foreground=P["text"],
                    borderwidth=1, bordercolor=P["border"],
                    padding=(12, 6), relief="flat", focuscolor=P["accent"])
    style.map("TButton",
              background=[("active", P["surface3"]), ("pressed", P["accent_dark"])],
              foreground=[("disabled", P["faint"]), ("pressed", "#ffffff")],
              bordercolor=[("active", P["border_hi"])])

    style.configure("Accent.TButton", background=P["accent"], foreground="#ffffff",
                    font=("Segoe UI", 11, "bold"), borderwidth=0,
                    padding=(16, 8))
    style.map("Accent.TButton",
              background=[("active", P["accent_hi"]), ("pressed", P["accent_dark"])],
              foreground=[("disabled", P["faint"])])

    # reusable affordance for small icon/utility buttons (unused by default)
    style.configure("Toolbutton", background=P["surface2"], foreground=P["muted"],
                    padding=(8, 4))
    style.map("Toolbutton",
              background=[("active", P["surface3"])],
              foreground=[("active", P["text"])])

    # ---- inputs --------------------------------------------------------
    style.configure("TEntry", fieldbackground=P["canvas_bg"],
                    foreground=P["text"], insertcolor=P["text"],
                    bordercolor=P["border"], padding=4)
    style.map("TEntry", bordercolor=[("focus", P["accent"])])

    style.configure("TCombobox", fieldbackground=P["canvas_bg"],
                    background=P["surface2"], foreground=P["text"],
                    arrowcolor=P["muted"], bordercolor=P["border"], padding=4)
    style.map("TCombobox",
              fieldbackground=[("readonly", P["canvas_bg"])],
              foreground=[("readonly", P["text"])],
              bordercolor=[("focus", P["accent"])],
              selectbackground=[("readonly", P["canvas_bg"])],
              selectforeground=[("readonly", P["text"])])
    root.option_add("*TCombobox*Listbox.background", P["canvas_bg"])
    root.option_add("*TCombobox*Listbox.foreground", P["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", P["accent"])
    root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
    root.option_add("*TCombobox*Listbox.borderWidth", 0)

    # ---- progress & scales --------------------------------------------
    style.configure("Horizontal.TProgressbar", background=P["accent"],
                    troughcolor=P["surface"], borderwidth=0, thickness=14)
    style.configure("Custom.Horizontal.TProgressbar", background=P["accent"],
                    troughcolor=P["surface"], borderwidth=0, thickness=20)
    style.configure("Horizontal.TScale", background=P["bg"],
                    troughcolor=P["surface"], sliderlength=18, sliderrelief="flat")
    style.map("Horizontal.TScale",
              background=[("active", P["bg"])],
              troughcolor=[("active", P["surface3"])])

    # ---- scrollbars & separators --------------------------------------
    style.configure("Vertical.TScrollbar", background=P["surface2"],
                    troughcolor=P["canvas_bg"], arrowcolor=P["muted"],
                    bordercolor=P["bg"], borderwidth=1)
    style.configure("TScrollbar", background=P["surface2"],
                    troughcolor=P["canvas_bg"], arrowcolor=P["muted"],
                    bordercolor=P["bg"], borderwidth=1)
    style.configure("TSeparator", background=P["border"])

    # ---- checks & radios ----------------------------------------------
    style.configure("TCheckbutton", background=P["bg"], foreground=P["text"])
    style.map("TCheckbutton",
              background=[("active", P["bg"])],
              foreground=[("disabled", P["faint"])])
    style.configure("TRadiobutton", background=P["bg"], foreground=P["text"])
    style.map("TRadiobutton",
              background=[("active", P["bg"])],
              foreground=[("disabled", P["faint"])])

    # ---- root window + dark title bar (Windows) -----------------------
    root.configure(bg=P["bg"])
    _apply_dark_titlebar(root)


def _apply_dark_titlebar(root: tk.Tk) -> None:
    """Make the Windows title bar dark (Win10 1809+ / Win11)."""
    if sys.platform != "win32":
        return
    try:
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (Win10 2004+) / 19 (older)
        value = ctypes.c_int(1)
        for attr in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                break
    except Exception:
        pass


def style_listbox(listbox: tk.Listbox) -> None:
    """Apply the dark theme to a plain tk.Listbox."""
    P = PALETTE
    listbox.configure(bg=P["canvas_bg"], fg=P["text"],
                      selectbackground=P["accent"], selectforeground="#ffffff",
                      highlightbackground=P["border"], highlightcolor=P["accent"],
                      highlightthickness=1, bd=0, relief="flat",
                      activestyle="none")
