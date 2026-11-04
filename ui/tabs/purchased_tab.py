"""
ui/tabs/purchased_tab.py
تبويب تطبيقات الحساب والمشتريات (Purchased & Owned Apps Tab)
المميزات:
- عرض جميع التطبيقات المملوكة للحساب مع أيقوناتها الدائرية
- التحميل الفوري من الكاش المحلي ثم التحديث التلقائي في الخلفية
- خيار "فحص الإصدارات": ينقل المستخدم مباشرة لتبويب استعراض وفحص الإصدارات مع تحميلها تلقائياً
- خيار "حفظ للتحميل لاحقاً": يضيف أحدث إصدار إلى قائمة التحميلات المحفوظة
- خيار "نسخ أمر التحميل": ينسخ أمر CMD للتطبيق إلى الحافظة
- خيار "تحميل أحدث إصدار": بدء التحميل المباشر للتطبيق
- زر "شراء ترخيص مجاني": الحصول على ترخيص أي تطبيق من المتجر مجاناً وربطه بالحساب
- شريط تصفية وبحث حي فوري بين تطبيقات الحساب
"""

import os
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from core.config import get_download_dir
from core.cache import load_purchases_cache
from core.queue_manager import add_to_saved_queue
from core.image_loader import load_app_icon_async
from core.apple_api import (
    get_account_purchases,
    get_latest_ext_id,
    generate_download_cmd,
    download_ipa,
    purchase_license
)
from core.utils import setup_entry_clipboard, format_size
from ui.styles import COLORS

class PurchasedTab:
    def __init__(self, app, notebook):
        self.app = app
        self.tab = ttk.Frame(notebook)
        notebook.add(self.tab, text="  تطبيقاتي المشتراة 🛍️  ")

        self.raw_apps = []
        self.filtered_apps = []
        self.card_widgets = []
        self.selected_index = -1
        self._image_refs = []
        self._is_loading = False

        self.build_ui()

        # Load initially from local cache for instant 0ms rendering
        initial_cache = load_purchases_cache()
        if initial_cache:
            self.raw_apps = initial_cache
            self.filtered_apps = list(initial_cache)
            self._render_cards()
            self.lbl_count_badge.config(text=f"({len(self.raw_apps)} تطبيق محفوظ)")

        # Auto-fetch in background on tab initialization
        self.app.root.after(800, self.on_refresh_purchases)

    def build_ui(self):
        # --- Top Control Bar ---
        top_bar = ttk.Frame(self.tab, style="Alt.TFrame")
        top_bar.pack(fill=tk.X, padx=12, pady=(10, 8))

        # Right side: Title & Actions
        self.lbl_title = ttk.Label(
            top_bar,
            text="تطبيقاتك المملوكة على حساب أبل 📱",
            style="Title.TLabel",
            anchor='e'
        )
        self.lbl_title.pack(side=tk.RIGHT, padx=10, pady=8)

        self.lbl_count_badge = tk.Label(
            top_bar,
            text="(جاري التحميل...)",
            bg=self.app.bg_color,
            fg=self.app.accent_color,
            font=("Segoe UI", 9, "bold"),
            padx=8,
            pady=3
        )
        self.lbl_count_badge.pack(side=tk.RIGHT, padx=5)

        # Buttons on Top
        self.btn_refresh = ttk.Button(
            top_bar,
            text="تحديث القائمة 🔄",
            command=self.on_refresh_purchases,
            style="Accent.TButton"
        )
        self.btn_refresh.pack(side=tk.LEFT, padx=6, pady=8)

        self.btn_purchase_license = ttk.Button(
            top_bar,
            text="الحصول على ترخيص مجاني 🛒",
            command=self.on_purchase_new_license
        )
        self.btn_purchase_license.pack(side=tk.LEFT, padx=6, pady=8)

        # --- Filter & Search Row ---
        filter_bar = ttk.Frame(self.tab)
        filter_bar.pack(fill=tk.X, padx=12, pady=(0, 8))

        lbl_filter_icon = ttk.Label(filter_bar, text="🔍 تصفية التطبيقات:", font=("Segoe UI", 10, "bold"))
        lbl_filter_icon.pack(side=tk.RIGHT, padx=(6, 0))

        self.entry_filter = ttk.Entry(filter_bar, justify='right', font=("Segoe UI", 10))
        self.entry_filter.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=8)
        self.entry_filter.insert(0, "ابحث باسم التطبيق أو معرف الحزمة (Bundle ID)...")
        self.entry_filter.bind("<FocusIn>", lambda e: self.entry_filter.delete(0, tk.END) if "ابحث باسم" in self.entry_filter.get() else None)
        self.entry_filter.bind("<KeyRelease>", self._on_filter_changed)
        setup_entry_clipboard(self.app.root, self.entry_filter)

        self.lbl_status = ttk.Label(filter_bar, text="", foreground=self.app.accent_color)
        self.lbl_status.pack(side=tk.LEFT, padx=5)

        # --- Middle: Scrollable Cards Canvas ---
        list_container = tk.Frame(self.tab, bg=self.app.bg_color)
        list_container.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 10))

        self.canvas = tk.Canvas(
            list_container,
            bg=self.app.bg_color,
            highlightthickness=0,
            borderwidth=0
        )
        self.scrollbar = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.canvas.yview)

        self.cards_frame = tk.Frame(self.canvas, bg=self.app.bg_color)
        self.cards_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas_window = self.canvas.create_window((0, 0), window=self.cards_frame, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width))

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.cards_frame.bind("<MouseWheel>", self._on_mousewheel)

        self._render_cards()

    def _bind_mousewheel(self, widget):
        widget.bind("<MouseWheel>", self._on_mousewheel)
        for child in widget.winfo_children():
            self._bind_mousewheel(child)

    def _on_mousewheel(self, event):
        if self.canvas.winfo_exists():
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # --- Actions & Logic ---

    def on_refresh_purchases(self):
        if self._is_loading:
            return
        self._is_loading = True
        self.btn_refresh.config(state=tk.DISABLED)
        self.lbl_status.config(text="جاري جلب التطبيقات المملوكة من حسابك في أبل... ⏳")
        self.app.log("جاري جلب قائمة التطبيقات المملوكة للحساب عبر ipatool...")
        self.app.run_in_thread(self._fetch_purchases_worker)

    def _fetch_purchases_worker(self):
        ok, msg, apps = get_account_purchases(retry_count=1)

        def update():
            self._is_loading = False
            self.btn_refresh.config(state=tk.NORMAL)
            if ok and apps:
                self.raw_apps = apps
                self._apply_filter()
                self.lbl_count_badge.config(text=f"({len(self.raw_apps)} تطبيق مملوك)")
                self.lbl_status.config(text="تم تحديث قائمة التطبيقات بنجاح ✅")
                self.app.log(f"تم جلب {len(apps)} تطبيق مملوك للحساب بنجاح.")
            else:
                self.lbl_status.config(text=f"تنبيه: {msg}")
                self.app.log(f"فشل جلب مشتريات الحساب: {msg}")
                # If we had cached apps, keep showing them
                if not self.raw_apps:
                    self._render_empty_state(msg)

        self.app.root.after(0, update)

    def _on_filter_changed(self, event=None):
        self._apply_filter()

    def _apply_filter(self):
        query = self.entry_filter.get().strip().lower()
        if not query or "ابحث باسم" in query:
            self.filtered_apps = list(self.raw_apps)
        else:
            self.filtered_apps = [
                a for a in self.raw_apps
                if query in a.get('name', '').lower()
                or query in a.get('bundle_id', '').lower()
                or query in a.get('seller', '').lower()
            ]

        self.selected_index = -1
        self._render_cards()

    def _render_empty_state(self, error_msg=""):
        for w in self.cards_frame.winfo_children():
            w.destroy()
        self.card_widgets.clear()

        msg = error_msg or "لم يتم العثور على أي تطبيقات مملوكة في هذا الحساب."
        f_empty = tk.Frame(self.cards_frame, bg=self.app.bg_color, pady=40)
        f_empty.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            f_empty,
            text="📱",
            font=("Segoe UI", 32),
            bg=self.app.bg_color,
            fg=self.app.accent_color
        ).pack()

        tk.Label(
            f_empty,
            text=msg,
            font=("Segoe UI", 11),
            bg=self.app.bg_color,
            fg=self.app.fg_color,
            pady=10
        ).pack()

        ttk.Button(
            f_empty,
            text="إعادة المحاولة 🔄",
            command=self.on_refresh_purchases,
            style="Accent.TButton"
        ).pack(pady=5)

    def _render_cards(self):
        for w in self.cards_frame.winfo_children():
            w.destroy()
        self.card_widgets.clear()

        if not self.filtered_apps:
            if not self.raw_apps:
                return
            no_match = tk.Label(
                self.cards_frame,
                text="لا توجد نتائج مطابقة لعبارة البحث.",
                bg=self.app.bg_color,
                fg=COLORS["sub_fg"],
                font=("Segoe UI", 11),
                pady=30
            )
            no_match.pack(fill=tk.X)
            return

        card_bg = "#262738"
        hover_bg = "#313247"
        border_color = "#36384f"

        for idx, app in enumerate(self.filtered_apps):
            # Outer Card Frame
            card = tk.Frame(
                self.cards_frame,
                bg=card_bg,
                highlightthickness=1,
                highlightbackground=border_color,
                padx=12,
                pady=10,
                cursor="hand2"
            )
            card.pack(fill=tk.X, pady=4, padx=2)

            # Left side: Action Buttons Container
            btn_box = tk.Frame(card, bg=card_bg)
            btn_box.pack(side=tk.LEFT, padx=(0, 6))

            # 1. Main Action: Check Versions (فحص واستعراض الإصدارات)
            btn_check_ver = ttk.Button(
                btn_box,
                text="فحص الإصدارات 🔍",
                command=lambda a=app: self.on_check_versions(a),
                style="Accent.TButton"
            )
            btn_check_ver.pack(side=tk.TOP, fill=tk.X, pady=2)

            # Secondary Action Buttons Row
            sec_btns = tk.Frame(btn_box, bg=card_bg)
            sec_btns.pack(side=tk.TOP, fill=tk.X, pady=(2, 0))

            btn_save_queue = ttk.Button(
                sec_btns,
                text="حفظ للتحميل لاحقاً 💾",
                command=lambda a=app: self.on_save_to_queue(a)
            )
            btn_save_queue.pack(side=tk.LEFT, padx=2)

            btn_copy_cmd = ttk.Button(
                sec_btns,
                text="نسخ أمر التحميل 📋",
                command=lambda a=app: self.on_copy_cmd(a)
            )
            btn_copy_cmd.pack(side=tk.LEFT, padx=2)

            btn_quick_dl = ttk.Button(
                sec_btns,
                text="تحميل فوري ⬇️",
                command=lambda a=app: self.on_direct_download(a)
            )
            btn_quick_dl.pack(side=tk.LEFT, padx=2)

            # Right side: App Icon
            lbl_icon = tk.Label(card, bg=card_bg, cursor="hand2")
            lbl_icon.pack(side=tk.RIGHT, padx=(12, 4))

            icon_url = app.get('icon_url', '')
            def on_icon_loaded(photo, target_lbl=lbl_icon):
                if target_lbl.winfo_exists():
                    target_lbl.config(image=photo)
                    target_lbl.image = photo
                    self._image_refs.append(photo)

            photo = load_app_icon_async(
                icon_url,
                self.app.root,
                size=(56, 56),
                radius=12,
                on_loaded_callback=on_icon_loaded
            )
            lbl_icon.config(image=photo)
            lbl_icon.image = photo
            self._image_refs.append(photo)

            # Center: Information Section
            info_frame = tk.Frame(card, bg=card_bg, cursor="hand2")
            info_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

            # Title Row
            row_title = tk.Frame(info_frame, bg=card_bg, cursor="hand2")
            row_title.pack(fill=tk.X, anchor='e')

            # Platforms badge
            platforms = app.get('platforms', [])
            plat_str = " / ".join(platforms) if platforms else "iOS"
            lbl_plat = tk.Label(
                row_title,
                text=f" {plat_str} ",
                bg=self.app.alt_bg,
                fg=COLORS["accent"],
                font=("Segoe UI", 8, "bold")
            )
            lbl_plat.pack(side=tk.LEFT, padx=(0, 6))

            price = app.get('price', 'مجاني')
            lbl_price = tk.Label(
                row_title,
                text=f" {price} ",
                bg=self.app.alt_bg,
                fg=COLORS["success"],
                font=("Segoe UI", 8, "bold")
            )
            lbl_price.pack(side=tk.LEFT, padx=(0, 6))

            app_name = app.get('name', 'تطبيق بدون اسم')
            lbl_name = tk.Label(
                row_title,
                text=app_name,
                bg=card_bg,
                fg=COLORS["fg"],
                font=("Segoe UI", 11, "bold"),
                anchor='e'
            )
            lbl_name.pack(side=tk.RIGHT)

            # Subtitle Row (Seller & Genre & Purchase Date)
            seller = app.get('seller', '')
            genres = app.get('genres', '')
            p_date = app.get('purchase_date', '')
            date_clean = p_date[:10] if p_date else ""

            sub_parts = []
            if seller: sub_parts.append(f"المطور: {seller}")
            if genres: sub_parts.append(genres)
            if date_clean: sub_parts.append(f"تاريخ الشراء: {date_clean}")
            sub_text = "   •   ".join(sub_parts) if sub_parts else "تطبيق مملوك للحساب"

            lbl_sub = tk.Label(
                info_frame,
                text=sub_text,
                bg=card_bg,
                fg=COLORS["sub_fg"],
                font=("Segoe UI", 9),
                anchor='e'
            )
            lbl_sub.pack(fill=tk.X, anchor='e', pady=(1, 2))

            # Details Row (Bundle ID, App ID, Version, Size, Min OS)
            bundle_id = app.get('bundle_id', '')
            app_id = app.get('app_id', '')
            version = app.get('current_version', '')
            ver_text = f"الإصدار: v{version}" if version else ""
            size_fmt = format_size(app.get('size', 0)) if app.get('size') and app.get('size') != '0' else ""
            min_os = app.get('min_os', '')
            min_os_text = f"iOS {min_os}+" if min_os else ""

            meta_parts = [p for p in [f"Bundle ID: {bundle_id}", f"App ID: {app_id}", ver_text, size_fmt, min_os_text] if p]
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

            # Bindings for hover, click & double click
            card_subwidgets = [
                card, lbl_icon, info_frame, row_title, lbl_name, lbl_sub, lbl_meta, btn_box, sec_btns
            ]

            def make_handlers(c_idx, c_frame, subs, a_item):
                def on_click(e):
                    self._highlight_card(c_idx)

                def on_dbl_click(e):
                    self.on_check_versions(a_item)

                def on_enter(e):
                    if self.selected_index != c_idx:
                        c_frame.configure(bg=hover_bg)
                        for w in subs:
                            try:
                                if w not in (lbl_plat, lbl_price, btn_check_ver, btn_save_queue, btn_copy_cmd, btn_quick_dl):
                                    w.configure(bg=hover_bg)
                            except Exception:
                                pass

                def on_leave(e):
                    if self.selected_index != c_idx:
                        c_frame.configure(bg=card_bg)
                        for w in subs:
                            try:
                                if w not in (lbl_plat, lbl_price, btn_check_ver, btn_save_queue, btn_copy_cmd, btn_quick_dl):
                                    w.configure(bg=card_bg)
                            except Exception:
                                pass

                return on_click, on_dbl_click, on_enter, on_leave

            c_clk, c_dbl, c_ent, c_lev = make_handlers(idx, card, card_subwidgets, app)

            for w in card_subwidgets:
                w.bind("<Button-1>", c_clk)
                w.bind("<Double-Button-1>", c_dbl)
                w.bind("<Enter>", c_ent)
                w.bind("<Leave>", c_lev)

            self._bind_mousewheel(card)
            self.card_widgets.append((card, card_subwidgets))

    def _highlight_card(self, index):
        if not self.filtered_apps or index < 0 or index >= len(self.filtered_apps):
            return

        card_bg = "#262738"
        sel_bg = "#35384f"
        accent = COLORS["accent"]
        border_normal = "#36384f"

        if 0 <= self.selected_index < len(self.card_widgets):
            old_card, old_subs = self.card_widgets[self.selected_index]
            if old_card.winfo_exists():
                old_card.configure(bg=card_bg, highlightbackground=border_normal, highlightthickness=1)
                for w in old_subs:
                    try:
                        w.configure(bg=card_bg)
                    except Exception:
                        pass

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

    # --- Feature: Check Versions & Switch to Tab (فحص واستعراض الإصدارات) ---

    def on_check_versions(self, app):
        """
        عند الضغط على فحص الإصدارات:
        1. يتم تعيين التطبيق فوراً كتطبيق حالي في البرنامج.
        2. يتم تحديث الكرت الرئيسي وأيقونته.
        3. يتم الانتقال فوراً في 0 ثانية إلى تبويب "استعراض وفحص الإصدارات".
        4. يتم جلب أحدث external version id وتحميل الإصدارات تلقائياً.
        """
        app_name = app.get('name', 'التطبيق')
        self.app.log(f"🔍 تم اختيار تطبيق «{app_name}» من المشتريات، جاري الانتقال إلى فحص الإصدارات...")

        app_data = {
            'app_id': app.get('app_id'),
            'bundle_id': app.get('bundle_id'),
            'name': app.get('name'),
            'icon_url': app.get('icon_url', ''),
            'seller': app.get('seller', ''),
            'genres': app.get('genres', ''),
            'price': app.get('price', 'Free'),
            'current_version': app.get('current_version', ''),
            'size': app.get('size', '0')
        }

        # 1. Set current app
        self.app.current_app = app_data
        self.app.current_latest_ext_id = None

        # 2. Update info card
        self.app._update_app_info()

        # 3. Switch tab immediately
        try:
            self.app.notebook.select(self.app.versions_tab.tab)
        except Exception:
            pass

        # 4. Fetch latest ext_id & trigger versions load
        def worker():
            ext_id, display_ver = get_latest_ext_id(app_data['app_id'])
            self.app.current_latest_ext_id = ext_id

            if display_ver and not app_data.get('current_version'):
                app_data['current_version'] = display_ver

            def update_and_load():
                self.app._update_app_info()
                self.app.on_load_versions()

            try:
                self.app.root.after(0, update_and_load)
            except Exception:
                pass

        self.app.run_in_thread(worker)

    # --- Feature: Save for download later (حفظ للتحميل لاحقاً) ---

    def on_save_to_queue(self, app):
        app_name = app.get('name', '')
        bundle_id = app.get('bundle_id', '')
        app_id = app.get('app_id', '')
        version = app.get('current_version', '?')

        self.app.log(f"💾 جاري حفظ تطبيق «{app_name}» في قائمة التحميلات...")

        def worker():
            ext_id = None
            if self.app.current_app and self.app.current_app.get('app_id') == app_id:
                ext_id = self.app.current_latest_ext_id
            if not ext_id:
                ext_id, _ = get_latest_ext_id(app_id)

            if not ext_id:
                ext_id = "latest"

            ok, msg = add_to_saved_queue(
                app_name=app_name,
                bundle_id=bundle_id,
                app_id=app_id,
                ext_id=ext_id,
                version=version,
                min_os="?"
            )

            def on_done():
                self.app.log(msg)
                self.app.refresh_saved_queue_ui()
                messagebox.showinfo("قائمة التحميل المحفوظة", f"✅ {msg}\n\nالتطبيق: {app_name}\nالإصدار: {version}")

            self.app.root.after(0, on_done)

        self.app.run_in_thread(worker)

    # --- Feature: Copy download command (نسخ أمر التحميل) ---

    def on_copy_cmd(self, app):
        app_name = app.get('name', '')
        bundle_id = app.get('bundle_id', '')
        app_id = app.get('app_id', '')
        version = app.get('current_version', '')

        self.app.log(f"📋 جاري إنشاء ونسخ أمر التحميل لتطبيق «{app_name}»...")

        def worker():
            ext_id = None
            if self.app.current_app and self.app.current_app.get('app_id') == app_id:
                ext_id = self.app.current_latest_ext_id
            if not ext_id:
                ext_id, _ = get_latest_ext_id(app_id)

            if not ext_id:
                ext_id = "0"

            cmd = generate_download_cmd(bundle_id, ext_id, app_name, version)
            self.app.root.after(0, lambda: self.app.copy_text_to_clipboard(cmd, f"تم نسخ أمر تحميل تطبيق {app_name}"))

        self.app.run_in_thread(worker)

    # --- Feature: Direct Download (التحميل المباشر) ---

    def on_direct_download(self, app):
        app_name = app.get('name', '')
        bundle_id = app.get('bundle_id', '')
        app_id = app.get('app_id', '')
        version = app.get('current_version', '')

        if not messagebox.askyesno("تأكيد التحميل", f"هل ترغب ببدء تحميل أحدث إصدار لتطبيق:\n{app_name} ({bundle_id})؟"):
            return

        self.app.log(f"⬇️ جاري تحضير تحميل تطبيق «{app_name}»...")

        def worker():
            ext_id, _ = get_latest_ext_id(app_id)
            if not ext_id:
                self.app.root.after(0, lambda: messagebox.showerror("خطأ", f"تعذر استخراج معرف أحدث إصدار لتطبيق {app_name}"))
                return

            clean_name = "".join(c for c in app_name if c.isalnum() or c in (' ', '_', '-')).strip().replace(" ", "_")
            out_file = os.path.join(get_download_dir(), f"{clean_name}_{ext_id}.ipa")

            def cb(msg):
                self.app.log(msg)

            success = download_ipa(bundle_id, ext_id, out_file, cb)
            def on_finish():
                if success:
                    messagebox.showinfo("تم التحميل", f"تم تحميل التطبيق بنجاح! ✅\nالمسار: {out_file}")
                else:
                    messagebox.showerror("فشل التحميل", f"فشل تحميل التطبيق. راجع سجل العمليات للتفاصيل ❌")

            self.app.root.after(0, on_finish)

        self.app.run_in_thread(worker)

    # --- Feature: Purchase New Free App License (شراء ترخيص مجاني) ---

    def on_purchase_new_license(self):
        bundle_id = simpledialog.askstring(
            "الحصول على ترخيص مجاني 🛒",
            "أدخل معرف الحزمة (Bundle ID) للتطبيق المجاني المطلوب ترخيصه:\n(مثال: com.google.ios.youtube أو net.whatsapp.WhatsApp)",
            parent=self.app.root
        )
        if not bundle_id or not bundle_id.strip():
            return

        bundle_id = bundle_id.strip()
        self.app.log(f"🛒 جاري طلب ترخيص مجاني للتطبيق: {bundle_id}...")

        def worker():
            ok, msg = purchase_license(bundle_id)
            self.app.log(msg)

            def on_done():
                if ok:
                    messagebox.showinfo("نجاح الترخيص", msg)
                    self.on_refresh_purchases()
                else:
                    messagebox.showerror("خطأ في الترخيص", f"تعذر ترخيص التطبيق:\n{msg}")

            self.app.root.after(0, on_done)

        self.app.run_in_thread(worker)
