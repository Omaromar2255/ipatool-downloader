"""
ui/search_dialog.py
نافذة عرض نتائج البحث عن التطبيقات مع الأيقونات (Search Results Dialog with App Icons)
المميزات:
- قائمة بطاقات تفاعلية أنيقة للتطبيقات
- عرض أيقونات التطبيقات بزوايا دائرية فائقة النعومة
- تحميل غير تزامني للأيقونات في الخلفية بدون أي تجميد
- دعم التمرير السلس بالماوس (MouseWheel)
- دعم التنقل بلوحة المفاتيح (الأسهم للأعلى وللأسفل، Enter للاختيار، Esc للإلغاء)
- النقر المزدوج للاختيار الفوري
- حقل تصفية سريع (Live Filter) للبحث السريع داخل النتائج
"""

import tkinter as tk
from tkinter import ttk
from core.image_loader import load_app_icon_async, get_placeholder_photo
from core.utils import format_size
from ui.styles import COLORS

class SearchResultsDialog:
    def __init__(self, parent, results, query, on_select_callback, colors=None):
        self.parent = parent
        self.raw_results = results
        self.filtered_results = list(results)
        self.query = query
        self.on_select_callback = on_select_callback
        self.colors = colors or COLORS

        self.selected_index = 0 if self.filtered_results else -1
        self.card_widgets = []
        self._image_refs = []  # Keep alive PhotoImages

        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title(f"نتائج البحث عن: {query}")
        self.dialog.geometry("780x600")
        self.dialog.minsize(640, 420)
        self.dialog.configure(bg=self.colors["bg"])
        self.dialog.transient(self.parent)
        self.dialog.grab_set()

        # Center on parent
        self._center_window()

        self._build_ui()
        self._bind_events()

        if self.filtered_results:
            self._highlight_card(0)

    def _center_window(self):
        self.dialog.update_idletasks()
        try:
            pw = self.parent.winfo_width()
            ph = self.parent.winfo_height()
            px = self.parent.winfo_rootx()
            py = self.parent.winfo_rooty()

            w = 780
            h = 600
            x = max(0, px + (pw - w) // 2)
            y = max(0, py + (ph - h) // 2)
            self.dialog.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

    def _build_ui(self):
        # --- Top Header ---
        header_frame = tk.Frame(self.dialog, bg=self.colors["bg"])
        header_frame.pack(fill=tk.X, padx=20, pady=(15, 10))

        # Title & Count Row
        title_row = tk.Frame(header_frame, bg=self.colors["bg"])
        title_row.pack(fill=tk.X)

        count_text = f"({len(self.raw_results)} تطبيق)"
        self.lbl_count = tk.Label(
            title_row,
            text=count_text,
            bg=self.colors["alt_bg"],
            fg=self.colors["accent"],
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=3
        )
        self.lbl_count.pack(side=tk.LEFT)

        lbl_title = tk.Label(
            title_row,
            text=f"🔍 نتائج البحث عن: «{self.query}»",
            bg=self.colors["bg"],
            fg=self.colors["fg"],
            font=("Segoe UI", 13, "bold"),
            anchor='e'
        )
        lbl_title.pack(side=tk.RIGHT, fill=tk.X, expand=True)

        # Subtitle & Filter Row
        sub_row = tk.Frame(header_frame, bg=self.colors["bg"])
        sub_row.pack(fill=tk.X, pady=(6, 0))

        # Live filter entry
        filter_frame = tk.Frame(sub_row, bg=self.colors["alt_bg"], padx=6, pady=2)
        filter_frame.pack(side=tk.LEFT)

        tk.Label(
            filter_frame,
            text="🔎",
            bg=self.colors["alt_bg"],
            fg=self.colors["sub_fg"],
            font=("Segoe UI", 9)
        ).pack(side=tk.LEFT, padx=(2, 4))

        self.entry_filter = tk.Entry(
            filter_frame,
            bg=self.colors["alt_bg"],
            fg=self.colors["fg"],
            insertbackground=self.colors["fg"],
            font=("Segoe UI", 9),
            width=22,
            relief="flat"
        )
        self.entry_filter.pack(side=tk.LEFT)
        self.entry_filter.insert(0, "تصفية النتائج...")
        self.entry_filter.bind("<FocusIn>", lambda e: self.entry_filter.delete(0, tk.END) if self.entry_filter.get() == "تصفية النتائج..." else None)
        self.entry_filter.bind("<KeyRelease>", self._on_filter_changed)

        lbl_sub = tk.Label(
            sub_row,
            text="انقر نقراً مزدوجاً على أي تطبيق لاختياره مباشرةً، أو حدده ثم اضغط «اختيار هذا التطبيق»",
            bg=self.colors["bg"],
            fg=self.colors["sub_fg"],
            font=("Segoe UI", 9),
            anchor='e'
        )
        lbl_sub.pack(side=tk.RIGHT, fill=tk.X, expand=True)

        # --- Bottom Action Bar (Packed first at bottom) ---
        bottom_frame = tk.Frame(self.dialog, bg=self.colors["alt_bg"], padx=15, pady=10)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)

        self.btn_select = ttk.Button(
            bottom_frame,
            text="اختيار هذا التطبيق ✅",
            command=self._confirm_selection,
            style="Accent.TButton"
        )
        self.btn_select.pack(side=tk.RIGHT, padx=(10, 0))

        btn_cancel = ttk.Button(
            bottom_frame,
            text="إلغاء ❌",
            command=self.dialog.destroy
        )
        btn_cancel.pack(side=tk.RIGHT)

        self.lbl_selected_hint = tk.Label(
            bottom_frame,
            text="اختر تطبيقاً من القائمة أعلاه",
            bg=self.colors["alt_bg"],
            fg=self.colors["sub_fg"],
            font=("Segoe UI", 9),
            anchor='w'
        )
        self.lbl_selected_hint.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # --- Middle: Scrollable Cards Canvas ---
        list_container = tk.Frame(self.dialog, bg=self.colors["bg"])
        list_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=20, pady=(0, 10))

        self.canvas = tk.Canvas(
            list_container,
            bg=self.colors["bg"],
            highlightthickness=0,
            borderwidth=0
        )
        self.scrollbar = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.canvas.yview)

        self.cards_frame = tk.Frame(self.canvas, bg=self.colors["bg"])
        self.cards_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas_window = self.canvas.create_window((0, 0), window=self.cards_frame, anchor="nw")
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self._render_cards()
        self.lbl_selected_hint.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def _bind_mousewheel(self, widget):
        widget.bind("<MouseWheel>", self._on_mousewheel)
        for child in widget.winfo_children():
            self._bind_mousewheel(child)

    def _on_mousewheel(self, event):
        if self.canvas.winfo_exists():
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _bind_events(self):
        self.dialog.bind("<Up>", self._on_key_up)
        self.dialog.bind("<Down>", self._on_key_down)
        self.dialog.bind("<Return>", lambda e: self._confirm_selection())
        self.dialog.bind("<Escape>", lambda e: self.dialog.destroy())

        # Also bind mousewheel on canvas
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.cards_frame.bind("<MouseWheel>", self._on_mousewheel)

    def _on_filter_changed(self, event=None):
        text = self.entry_filter.get().strip().lower()
        if not text or text == "تصفية النتائج...":
            self.filtered_results = list(self.raw_results)
        else:
            self.filtered_results = [
                app for app in self.raw_results
                if text in app.get('name', '').lower()
                or text in app.get('bundle_id', '').lower()
                or text in app.get('seller', '').lower()
            ]

        self.lbl_count.config(text=f"({len(self.filtered_results)} من أصل {len(self.raw_results)})")
        self.selected_index = 0 if self.filtered_results else -1
        self._render_cards()
        if self.filtered_results:
            self._highlight_card(0)

    def _render_cards(self):
        # Clear existing cards
        for w in self.cards_frame.winfo_children():
            w.destroy()
        self.card_widgets.clear()

        if not self.filtered_results:
            no_res = tk.Label(
                self.cards_frame,
                text="لا توجد نتائج مطابقة للبحث أو التصفية.",
                bg=self.colors["bg"],
                fg=self.colors["sub_fg"],
                font=("Segoe UI", 11),
                pady=40
            )
            no_res.pack(fill=tk.X)
            self.btn_select.config(state=tk.DISABLED)
            self.lbl_selected_hint.config(text="لا توجد عناصر مختارة")
            return

        self.btn_select.config(state=tk.NORMAL)

        card_bg = "#262738"
        hover_bg = "#313247"
        border_color = "#36384f"

        for idx, app in enumerate(self.filtered_results):
            # Outer Card Frame
            card = tk.Frame(
                self.cards_frame,
                bg=card_bg,
                highlightthickness=1,
                highlightbackground=border_color,
                highlightcolor=self.colors["accent"],
                padx=12,
                pady=10,
                cursor="hand2"
            )
            card.pack(fill=tk.X, pady=4, padx=2)

            # Left side: Action Button (اختيار)
            btn_choose = ttk.Button(
                card,
                text="اختيار ✅",
                command=lambda a=app: self._select_and_close(a),
                style="Accent.TButton"
            )
            btn_choose.pack(side=tk.LEFT, padx=(0, 10))

            # Right side: App Icon (56x56 rounded)
            lbl_icon = tk.Label(
                card,
                bg=card_bg,
                cursor="hand2"
            )
            lbl_icon.pack(side=tk.RIGHT, padx=(12, 4))

            # Load Icon Async
            icon_url = app.get('icon_url', '')
            def on_icon_loaded(photo, target_lbl=lbl_icon):
                if target_lbl.winfo_exists():
                    target_lbl.config(image=photo)
                    target_lbl.image = photo
                    self._image_refs.append(photo)

            initial_photo = load_app_icon_async(
                icon_url,
                self.dialog,
                size=(56, 56),
                radius=12,
                on_loaded_callback=on_icon_loaded
            )
            lbl_icon.config(image=initial_photo)
            lbl_icon.image = initial_photo
            self._image_refs.append(initial_photo)

            # Center: Info Section (Title, Developer, Metadata)
            info_frame = tk.Frame(card, bg=card_bg, cursor="hand2")
            info_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

            # Title Row
            row_title = tk.Frame(info_frame, bg=card_bg, cursor="hand2")
            row_title.pack(fill=tk.X, anchor='e')

            # Price badge
            price = app.get('price', 'Free')
            price_color = self.colors["success"] if ("free" in str(price).lower() or "مجاني" in str(price)) else self.colors["accent"]
            lbl_price = tk.Label(
                row_title,
                text=f" {price} ",
                bg=self.colors["alt_bg"],
                fg=price_color,
                font=("Segoe UI", 8, "bold")
            )
            lbl_price.pack(side=tk.LEFT, padx=(0, 6))

            app_name = app.get('name', 'تطبيق غير معروف')
            lbl_name = tk.Label(
                row_title,
                text=app_name,
                bg=card_bg,
                fg=self.colors["fg"],
                font=("Segoe UI", 11, "bold"),
                anchor='e'
            )
            lbl_name.pack(side=tk.RIGHT)

            # Subtitle Row (Seller & Genre)
            seller = app.get('seller', '')
            genres = app.get('genres', '')
            sub_text_parts = [p for p in [seller, genres] if p]
            sub_text = "  •  ".join(sub_text_parts) if sub_text_parts else "تطبيق iOS"

            lbl_sub = tk.Label(
                info_frame,
                text=sub_text,
                bg=card_bg,
                fg=self.colors["sub_fg"],
                font=("Segoe UI", 9),
                anchor='e'
            )
            lbl_sub.pack(fill=tk.X, anchor='e', pady=(1, 2))

            # Details Row (Bundle ID, Version, Size, Min OS)
            bundle_id = app.get('bundle_id', '')
            version = app.get('current_version', '')
            ver_text = f"v{version}" if version else ""
            size_fmt = format_size(app.get('size', 0))
            min_os = app.get('min_os', '')
            min_os_text = f"iOS {min_os}+" if min_os else ""
            rating = app.get('rating')
            rating_text = f"★ {rating:.1f}" if rating else ""

            meta_parts = [p for p in [bundle_id, ver_text, size_fmt, min_os_text, rating_text] if p]
            meta_text = "   |   ".join(meta_parts)

            lbl_meta = tk.Label(
                info_frame,
                text=meta_text,
                bg=card_bg,
                fg="#89b4fa",
                font=("Segoe UI", 8),
                anchor='e'
            )
            lbl_meta.pack(fill=tk.X, anchor='e')

            # Collect subwidgets for styling
            card_subwidgets = [
                card, lbl_icon, info_frame, row_title, lbl_name, lbl_sub, lbl_meta
            ]

            # Click & Hover bindings
            def make_card_handlers(card_idx, c_frame, subs):
                def on_click(e):
                    self._highlight_card(card_idx)

                def on_double_click(e):
                    if 0 <= card_idx < len(self.filtered_results):
                        self._select_and_close(self.filtered_results[card_idx])

                def on_enter(e):
                    if self.selected_index != card_idx:
                        c_frame.configure(bg=hover_bg)
                        for w in subs:
                            try:
                                if w not in (lbl_price,):
                                    w.configure(bg=hover_bg)
                            except Exception:
                                pass

                def on_leave(e):
                    if self.selected_index != card_idx:
                        c_frame.configure(bg=card_bg)
                        for w in subs:
                            try:
                                if w not in (lbl_price,):
                                    w.configure(bg=card_bg)
                            except Exception:
                                pass

                return on_click, on_double_click, on_enter, on_leave

            c_click, c_dbl, c_enter, c_leave = make_card_handlers(idx, card, card_subwidgets)

            for w in card_subwidgets:
                w.bind("<Button-1>", c_click)
                w.bind("<Double-Button-1>", c_dbl)
                w.bind("<Enter>", c_enter)
                w.bind("<Leave>", c_leave)

            self._bind_mousewheel(card)
            self.card_widgets.append((card, card_subwidgets))

    def _highlight_card(self, index):
        if not self.filtered_results or index < 0 or index >= len(self.filtered_results):
            return

        card_bg = "#262738"
        sel_bg = "#35384f"
        accent = self.colors["accent"]
        border_normal = "#36384f"

        # Reset previous selection
        if 0 <= self.selected_index < len(self.card_widgets):
            old_card, old_subs = self.card_widgets[self.selected_index]
            if old_card.winfo_exists():
                old_card.configure(bg=card_bg, highlightbackground=border_normal, highlightthickness=1)
                for w in old_subs:
                    try:
                        w.configure(bg=card_bg)
                    except Exception:
                        pass

        # Apply new selection
        self.selected_index = index
        if 0 <= index < len(self.card_widgets):
            new_card, new_subs = self.card_widgets[index]
            if new_card.winfo_exists():
                new_card.configure(bg=sel_bg, highlightbackground=accent, highlightthickness=2)
                for w in new_subs:
                    try:
                        w.configure(bg=sel_bg)
                    except Exception:
                        pass

            selected_app = self.filtered_results[index]
            self.lbl_selected_hint.config(
                text=f"المحدد: {selected_app.get('name')} ({selected_app.get('bundle_id')})",
                fg=self.colors["fg"]
            )

    def _scroll_to_card(self, index):
        if not self.card_widgets or index < 0 or index >= len(self.card_widgets):
            return
        try:
            self.dialog.update_idletasks()
            total_cards = len(self.card_widgets)
            if total_cards > 1:
                fraction = index / (total_cards - 1)
                self.canvas.yview_moveto(max(0.0, min(1.0, fraction - 0.15)))
        except Exception:
            pass

    def _on_key_up(self, event):
        if self.selected_index > 0:
            self._highlight_card(self.selected_index - 1)
            self._scroll_to_card(self.selected_index)
        return "break"

    def _on_key_down(self, event):
        if self.selected_index < len(self.filtered_results) - 1:
            self._highlight_card(self.selected_index + 1)
            self._scroll_to_card(self.selected_index)
        return "break"

    def _confirm_selection(self):
        if 0 <= self.selected_index < len(self.filtered_results):
            app = self.filtered_results[self.selected_index]
            self._select_and_close(app)

    def _select_and_close(self, app):
        try:
            self.dialog.destroy()
        except Exception:
            pass
        if self.on_select_callback:
            self.on_select_callback(app)
