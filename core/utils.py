import tkinter as tk

def parse_os(os_str):
    try:
        return [int(x) for x in str(os_str).split('.') if x.isdigit()]
    except Exception:
        return [99]

def is_os_le(v1_str, v2_str):
    p1 = parse_os(v1_str)
    p2 = parse_os(v2_str)
    while len(p1) < len(p2): p1.append(0)
    while len(p2) < len(p1): p2.append(0)
    return p1 <= p2

def format_size(size_bytes):
    try:
        size_bytes = float(size_bytes)
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
    except Exception:
        return "غير معروف"

# --- Keyboard & Context Menu Helpers for Entry Widgets ---

def setup_entry_clipboard(root, entry):
    menu = tk.Menu(root, tearoff=0, bg="#313244", fg="#cdd6f4")
    menu.add_command(label="قص (Cut)", command=lambda: entry.event_generate("<<Cut>>"))
    menu.add_command(label="نسخ (Copy)", command=lambda: entry.event_generate("<<Copy>>"))
    menu.add_command(label="لصق (Paste)", command=lambda: entry.event_generate("<<Paste>>"))
    menu.add_separator()
    menu.add_command(label="تحديد الكل (Select All)", command=lambda: (entry.select_range(0, tk.END), entry.icursor(tk.END)))
    menu.add_command(label="مسح (Clear)", command=lambda: entry.delete(0, tk.END))

    def show_popup(event):
        menu.post(event.x_root, event.y_root)

    entry.bind("<Button-3>", show_popup)

    def on_ctrl_press(event):
        if event.keycode == 86: # V
            try:
                clip = root.clipboard_get()
                try:
                    s_first = entry.index(tk.SEL_FIRST)
                    s_last = entry.index(tk.SEL_LAST)
                    entry.delete(s_first, s_last)
                except tk.TclError:
                    pass
                entry.insert(tk.INSERT, clip)
                return "break"
            except Exception:
                pass
        elif event.keycode == 67: # C
            try:
                sel = entry.selection_get()
                root.clipboard_clear()
                root.clipboard_append(sel)
                return "break"
            except Exception:
                pass
        elif event.keycode == 88: # X
            try:
                sel = entry.selection_get()
                root.clipboard_clear()
                root.clipboard_append(sel)
                s_first = entry.index(tk.SEL_FIRST)
                s_last = entry.index(tk.SEL_LAST)
                entry.delete(s_first, s_last)
                return "break"
            except Exception:
                pass
        elif event.keycode == 65: # A
            entry.select_range(0, tk.END)
            entry.icursor(tk.END)
            return "break"

    entry.bind("<Control-KeyPress>", on_ctrl_press)
