import tkinter as tk
from tkinter import ttk

# --- Color Scheme & Styles ---
COLORS = {
    "bg": "#1e1e2e",
    "fg": "#cdd6f4",
    "accent": "#89b4fa",
    "alt_bg": "#313244",
    "success": "#a6e3a1",
    "danger": "#f38ba8",
    "sub_fg": "#a6adc8",
    "dark_text": "#11111b"
}

def setup_styles(theme_colors=None):
    if theme_colors is None:
        theme_colors = COLORS

    style = ttk.Style()
    style.theme_use("clam")

    bg = theme_colors["bg"]
    fg = theme_colors["fg"]
    accent = theme_colors["accent"]
    alt_bg = theme_colors["alt_bg"]
    success = theme_colors["success"]
    danger = theme_colors["danger"]
    sub_fg = theme_colors["sub_fg"]
    dark_text = theme_colors["dark_text"]

    style.configure(".", background=bg, foreground=fg, font=("Segoe UI", 10))
    style.configure("TFrame", background=bg)
    style.configure("Alt.TFrame", background=alt_bg)

    style.configure("TLabel", background=bg, foreground=fg)
    style.configure("Header.TLabel", font=("Segoe UI", 11, "bold"))
    style.configure("Title.TLabel", font=("Segoe UI", 13, "bold"), foreground=accent)
    style.configure("Sub.TLabel", font=("Segoe UI", 9), foreground=sub_fg)

    style.configure("TButton", background=alt_bg, foreground=fg, borderwidth=1, focuscolor=accent)
    style.map("TButton", background=[("active", accent)], foreground=[("active", bg)])
    style.configure("Accent.TButton", background=accent, foreground=bg, font=("Segoe UI", 10, "bold"))
    style.configure("Success.TButton", background=success, foreground=dark_text, font=("Segoe UI", 10, "bold"))
    style.configure("Danger.TButton", background=danger, foreground=bg, font=("Segoe UI", 10, "bold"))

    style.configure("TEntry", fieldbackground=alt_bg, foreground=fg, insertcolor=fg, borderwidth=1)

    style.configure("TNotebook", background=bg, borderwidth=0)
    style.configure("TNotebook.Tab", background=alt_bg, foreground=fg, padding=[14, 6])
    style.map("TNotebook.Tab", background=[("selected", accent)], foreground=[("selected", bg)])

    style.configure("Treeview", background=alt_bg, foreground=fg, fieldbackground=alt_bg, borderwidth=0, font=("Segoe UI", 10))
    style.configure("Treeview.Heading", background=bg, foreground=accent, font=("Segoe UI", 10, "bold"))
    style.map("Treeview", background=[("selected", accent)], foreground=[("selected", bg)])

    style.configure("Horizontal.TProgressbar", background=accent, troughcolor=alt_bg)
