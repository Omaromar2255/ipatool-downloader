import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
from core.config import get_download_dir
from core.apple_api import search_app, get_latest_ext_id, generate_download_cmd
from core.queue_manager import add_to_saved_queue
from core.utils import setup_entry_clipboard, format_size
from core.image_loader import load_app_icon_async, get_placeholder_photo
from .styles import COLORS, setup_styles
from .search_dialog import SearchResultsDialog
from .tabs.quick_tab import QuickTab
from .tabs.purchased_tab import PurchasedTab
from .tabs.versions_tab import VersionsTab
from .tabs.compatible_tab import CompatibleTab
from .tabs.queue_tab import QueueTab
from .tabs.account_tab import AccountTab

class IPAManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("مدير تطبيقات IPA (الشامل: كاش + فحص متوازي + قائمة التحميل + تسجيل الدخول)")
        self.root.geometry("1060x820")

        # Color Scheme
        self.bg_color = COLORS["bg"]
        self.fg_color = COLORS["fg"]
        self.accent_color = COLORS["accent"]
        self.alt_bg = COLORS["alt_bg"]
        self.success_color = COLORS["success"]
        self.danger_color = COLORS["danger"]

        self.root.configure(bg=self.bg_color)

        # App State
        self.current_app = None
        self.current_latest_ext_id = None
        self.current_versions = []
        self._search_results = []

        setup_styles(COLORS)
        self.build_ui()
        self.refresh_saved_queue_ui()
        self.refresh_account_status_ui()

    def build_ui(self):
        # --- Top: Search Bar ---
        top_frame = ttk.Frame(self.root)
        top_frame.pack(fill=tk.X, padx=20, pady=(15, 8))

        self.btn_search = ttk.Button(
            top_frame,
            text="بحث 🔍",
            command=self.on_search,
            style="Accent.TButton"
        )
        self.btn_search.pack(side=tk.RIGHT, padx=(10, 0))

        self.entry_search = ttk.Entry(top_frame, justify='right', font=("Segoe UI", 11))
        self.entry_search.pack(side=tk.RIGHT, fill=tk.X, expand=True)
        self.entry_search.insert(0, "ابحث عن تطبيق... (اسم مثل youtube أو instagram أو bundleId)")
        self.entry_search.bind("<FocusIn>", lambda e: self.entry_search.delete(0, tk.END) if "ابحث عن" in self.entry_search.get() else None)
        self.entry_search.bind("<Return>", lambda e: self.on_search())

        setup_entry_clipboard(self.root, self.entry_search)

        # --- Middle: App Info + Tabs ---
        self.middle_frame = ttk.Frame(self.root)
        self.middle_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 10))

        # App Info Card
        self.info_card = ttk.Frame(self.middle_frame, style="Alt.TFrame")
        self.info_card.pack(fill=tk.X, pady=(0, 8))

        self.info_content_frame = tk.Frame(self.info_card, bg=self.alt_bg)
        self.info_content_frame.pack(fill=tk.X, padx=15, pady=(10, 6))

        # App Icon Label on the right (RTL layout)
        self.lbl_app_icon = tk.Label(self.info_content_frame, bg=self.alt_bg)
        self.lbl_app_icon.pack(side=tk.RIGHT, padx=(15, 0))
        self._initial_app_icon = get_placeholder_photo(size=(64, 64), radius=14)
        self.lbl_app_icon.config(image=self._initial_app_icon)
        self.lbl_app_icon.image = self._initial_app_icon

        # Text Frame beside Icon
        self.info_text_frame = tk.Frame(self.info_content_frame, bg=self.alt_bg)
        self.info_text_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.lbl_app_name = ttk.Label(self.info_text_frame, text="", style="Title.TLabel", anchor='e')
        self.lbl_app_name.pack(fill=tk.X, pady=(0, 2))

        self.lbl_app_details = ttk.Label(
            self.info_text_frame,
            text="يرجى كتابة اسم التطبيق والضغط على بحث (يدعم النسخ واللصق الكامل)",
            anchor='e',
            justify='right'
        )
        self.lbl_app_details.pack(fill=tk.X, pady=(0, 4))

        # Quick action buttons for loaded app
        self.info_btn_frame = ttk.Frame(self.info_card, style="Alt.TFrame")
        self.info_btn_frame.pack(fill=tk.X, padx=15, pady=(0, 8))

        self.btn_save_latest = ttk.Button(
            self.info_btn_frame,
            text="حفظ أحدث إصدار للتحميل لاحقاً 💾",
            command=self.on_save_latest_to_queue
        )
        self.btn_save_latest.pack(side=tk.RIGHT, padx=5)

        self.btn_copy_latest_cmd = ttk.Button(
            self.info_btn_frame,
            text="نسخ أمر التحميل (CMD) 📋",
            command=self.on_copy_latest_cmd
        )
        self.btn_copy_latest_cmd.pack(side=tk.RIGHT, padx=5)

        self.info_btn_frame.pack_forget()

        # Tabs Notebook
        self.notebook = ttk.Notebook(self.middle_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Instantiate Tabs
        self.quick_tab = QuickTab(self, self.notebook)
        self.purchased_tab = PurchasedTab(self, self.notebook)
        self.versions_tab = VersionsTab(self, self.notebook)
        self.compatible_tab = CompatibleTab(self, self.notebook)
        self.queue_tab = QueueTab(self, self.notebook)
        self.account_tab = AccountTab(self, self.notebook)

        # Compatibility proxies for widgets
        self.tree = self.versions_tab.tree
        self.queue_tree = self.queue_tab.queue_tree
        self.btn_quick_download = self.quick_tab.btn_quick_download
        self.lbl_quick_status = self.quick_tab.lbl_quick_status
        self.btn_load_versions = self.versions_tab.btn_load_versions
        self.lbl_versions_count = self.versions_tab.lbl_versions_count
        self.btn_scan_top_n = self.versions_tab.btn_scan_top_n
        self.btn_scan_range = self.versions_tab.btn_scan_range
        self.btn_cancel_scan = self.versions_tab.btn_cancel_scan
        self.scan_prog_bar = self.versions_tab.scan_prog_bar
        self.lbl_scan_status = self.versions_tab.lbl_scan_status
        self.entry_range_from = self.versions_tab.entry_range_from
        self.entry_range_to = self.versions_tab.entry_range_to
        self.btn_auto_search = self.compatible_tab.btn_auto_search
        self.lbl_search_result = self.compatible_tab.lbl_search_result
        self.compat_btn_frame = self.compatible_tab.compat_btn_frame
        self.btn_download_compatible = self.compatible_tab.btn_download_compatible
        self.btn_queue_download_sel = self.queue_tab.btn_queue_download_sel
        self.btn_queue_download_all = self.queue_tab.btn_queue_download_all
        self.btn_queue_stop = self.queue_tab.btn_queue_stop
        self.lbl_acc_status_badge = self.account_tab.lbl_acc_status_badge
        self.lbl_acc_name_email = self.account_tab.lbl_acc_name_email

        # --- Bottom: Console ---
        bottom_frame = ttk.Frame(self.root)
        bottom_frame.pack(fill=tk.X, padx=20, pady=(0, 12))

        console_header = ttk.Frame(bottom_frame)
        console_header.pack(fill=tk.X)

        ttk.Label(console_header, text="سجل العمليات:", style="Header.TLabel").pack(side=tk.RIGHT)
        ttk.Button(console_header, text="مسح السجل 🗑️", command=self.clear_console_logs).pack(side=tk.LEFT)
        ttk.Button(console_header, text="نسخ السجلات 📋", command=self.copy_console_logs).pack(side=tk.LEFT, padx=(0, 6))

        self.console = scrolledtext.ScrolledText(
            bottom_frame,
            height=5,
            bg=self.alt_bg,
            fg=self.fg_color,
            insertbackground=self.fg_color,
            font=("Consolas", 9)
        )
        self.console.pack(fill=tk.X, pady=(4, 0))
        self._setup_console_context_menu()

    # --- Clipboard & Utilities ---

    def _setup_console_context_menu(self):
        menu = tk.Menu(self.root, tearoff=0, bg=self.alt_bg, fg=self.fg_color)
        menu.add_command(label="نسخ السجلات (Copy All)", command=self.copy_all_logs)
        menu.add_command(label="نسخ المحدد (Copy Selection)", command=self.copy_selected_logs)
        menu.add_separator()
        menu.add_command(label="تحديد الكل (Select All)", command=self.select_all_logs)
        menu.add_command(label="مسح السجل (Clear)", command=self.clear_console_logs)

        def show_popup(event):
            try:
                menu.post(event.x_root, event.y_root)
            except Exception:
                pass

        self.console.bind("<Button-3>", show_popup)

        def on_key(event):
            # Allow Ctrl+C (keycode 67 / keysym 'c'/'C')
            if (event.state & 0x4 or event.state & 0x20000) and (event.keysym.lower() == 'c' or event.keycode == 67):
                self.copy_console_logs()
                return "break"
            # Allow Ctrl+A (keycode 65 / keysym 'a'/'A')
            if (event.state & 0x4 or event.state & 0x20000) and (event.keysym.lower() == 'a' or event.keycode == 65):
                self.select_all_logs()
                return "break"
            # Allow navigation keys
            if event.keysym in ('Up', 'Down', 'Left', 'Right', 'Prior', 'Next', 'Home', 'End'):
                return None
            # Block modifications
            return "break"

        self.console.bind("<Key>", on_key)

    def copy_console_logs(self):
        """نسخ النص المحدد إن وجد، وإلا نسخ كامل السجلات."""
        try:
            content = self.console.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            content = None

        if not content:
            content = self.console.get("1.0", tk.END).strip()

        if not content:
            messagebox.showinfo("نسخ السجلات", "سجل العمليات فارغ حالياً.")
            return

        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self.root.update()
        self.log("📋 تم نسخ السجلات إلى الحافظة بنجاح.")

    def copy_all_logs(self):
        content = self.console.get("1.0", tk.END).strip()
        if not content:
            messagebox.showinfo("نسخ السجلات", "سجل العمليات فارغ حالياً.")
            return

        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self.root.update()
        self.log("📋 تم نسخ كامل السجلات إلى الحافظة بنجاح.")

    def copy_selected_logs(self):
        try:
            content = self.console.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            content = None

        if not content:
            messagebox.showinfo("نسخ السجلات", "لم تقم بتحديد أي نص من السجل.")
            return

        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self.root.update()
        self.log("📋 تم نسخ النص المحدد إلى الحافظة بنجاح.")

    def select_all_logs(self):
        self.console.tag_add(tk.SEL, "1.0", tk.END)
        self.console.mark_set(tk.INSERT, "1.0")
        self.console.see(tk.INSERT)
        return "break"

    def clear_console_logs(self):
        self.console.delete("1.0", tk.END)

    def copy_text_to_clipboard(self, text, message="تم نسخ النص إلى الحافظة!"):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()
        self.log(f"📋 {message}")
        messagebox.showinfo("تم النسخ", f"{message}\n\nالأمر المنسوخ:\n{text}")

    def log(self, message):
        def update():
            self.console.insert(tk.END, f"> {message}\n")
            self.console.see(tk.END)
        self.root.after(0, update)

    def run_in_thread(self, func, *args):
        threading.Thread(target=func, args=args, daemon=True).start()

    # --- Search Actions ---

    def on_search(self):
        query = self.entry_search.get().strip()
        if not query or "ابحث عن" in query:
            return

        self.btn_search.config(state=tk.DISABLED)
        self.log(f"جاري البحث عن: {query}...")
        self.run_in_thread(self._search_worker, query)

    def _search_worker(self, query):
        try:
            results = search_app(query)
            if not results:
                self.root.after(0, lambda: self.log("لم يتم العثور على نتائج."))
                self.root.after(0, lambda: messagebox.showinfo("بحث", "لم يتم العثور على أي تطبيق يطابق البحث."))
                return

            if not isinstance(results, list):
                results = [results]

            self.log(f"تم العثور على {len(results)} نتيجة.")
            self._search_results = results
            self.root.after(0, lambda: self._show_results_dialog(query))

        except Exception as e:
            self.log(f"خطأ أثناء البحث: {str(e)}")
        finally:
            self.root.after(0, lambda: self.btn_search.config(state=tk.NORMAL))

    def _show_results_dialog(self, query=""):
        if not self._search_results:
            return

        SearchResultsDialog(
            parent=self.root,
            results=self._search_results,
            query=query or self.entry_search.get().strip(),
            on_select_callback=lambda app: self.run_in_thread(self._select_app, app),
            colors=COLORS
        )

    def _select_app(self, app):
        self.current_app = app
        self.log(f"تم اختيار التطبيق: {app['name']}")

        ext_id, display_ver = get_latest_ext_id(app['app_id'])
        self.current_latest_ext_id = ext_id

        if display_ver and not app.get('current_version'):
            app['current_version'] = display_ver

        self.root.after(0, self._update_app_info)
        self.root.after(0, lambda: self.btn_search.config(state=tk.NORMAL))

    def _update_app_info(self):
        app = self.current_app
        size_fmt = format_size(app.get('size', 0))
        self.lbl_app_name.config(text=app.get('name', ''))

        details = (
            f"Bundle ID: {app.get('bundle_id')}   |   App ID: {app.get('app_id')}\n"
            f"المطور: {app.get('seller')}   |   أحدث إصدار: {app.get('current_version')} (معرف: {self.current_latest_ext_id})\n"
            f"الحجم: {size_fmt}   |   السعر: {app.get('price')}"
        )
        self.lbl_app_details.config(text=details)
        self.info_btn_frame.pack(fill=tk.X, padx=15, pady=(0, 8))

        # Update app icon with 64x64 rounded icon
        icon_url = app.get('icon_url', '')
        def on_icon_ready(photo):
            if self.lbl_app_icon.winfo_exists():
                self.lbl_app_icon.config(image=photo)
                self.lbl_app_icon.image = photo

        loaded_photo = load_app_icon_async(
            icon_url,
            self.root,
            size=(64, 64),
            radius=14,
            on_loaded_callback=on_icon_ready
        )
        self.lbl_app_icon.config(image=loaded_photo)
        self.lbl_app_icon.image = loaded_photo

        # Reset tabs
        self.versions_tab.clear()
        self.current_versions = []
        self.lbl_quick_status.config(text="جاهز للتحميل")
        self.compatible_tab.clear()
        self.scan_prog_bar['value'] = 0
        self.lbl_scan_status.config(text="")

    def on_save_latest_to_queue(self):
        if not self.current_app or not self.current_latest_ext_id:
            messagebox.showwarning("تنبيه", "يرجى البحث عن تطبيق أولاً")
            return
        app = self.current_app
        ok, msg = add_to_saved_queue(
            app_name=app['name'],
            bundle_id=app['bundle_id'],
            app_id=app['app_id'],
            ext_id=self.current_latest_ext_id,
            version=app.get('current_version', '?'),
            min_os="?"
        )
        self.log(msg)
        self.refresh_saved_queue_ui()
        messagebox.showinfo("قائمة التنزيل المحفوظة", msg)

    def on_copy_latest_cmd(self):
        if not self.current_app or not self.current_latest_ext_id:
            messagebox.showwarning("تنبيه", "يرجى البحث عن تطبيق أولاً")
            return
        app = self.current_app
        cmd = generate_download_cmd(app['bundle_id'], self.current_latest_ext_id, app['name'], app.get('current_version', ''))
        self.copy_text_to_clipboard(cmd, f"تم نسخ أمر تحميل أحدث إصدار لتطبيق {app['name']}")

    # --- Delegate Methods for Backward Compatibility ---

    def refresh_saved_queue_ui(self):
        if hasattr(self, 'queue_tab'):
            self.queue_tab.refresh_saved_queue_ui()

    def refresh_account_status_ui(self):
        if hasattr(self, 'account_tab'):
            self.account_tab.refresh_account_status_ui()

    def on_quick_download(self):
        self.quick_tab.on_quick_download()

    def on_load_versions(self):
        self.versions_tab.on_load_versions()

    def on_check_compatibility(self):
        self.versions_tab.on_check_compatibility()

    def on_download_selected(self):
        self.versions_tab.on_download_selected()

    def on_save_selected_to_queue(self):
        self.versions_tab.on_save_selected_to_queue()

    def on_copy_selected_cmd(self):
        self.versions_tab.on_copy_selected_cmd()

    def on_scan_top_n(self):
        self.versions_tab.on_scan_top_n()

    def on_scan_range(self):
        self.versions_tab.on_scan_range()

    def on_cancel_scan(self):
        self.versions_tab.on_cancel_scan()

    def on_auto_search(self):
        self.compatible_tab.on_auto_search()

    def on_download_compatible(self):
        self.compatible_tab.on_download_compatible()

    def on_save_compatible_to_queue(self):
        self.compatible_tab.on_save_compatible_to_queue()

    def on_copy_compatible_cmd(self):
        self.compatible_tab.on_copy_compatible_cmd()

    def on_queue_copy_cmd(self):
        self.queue_tab.on_queue_copy_cmd()

    def on_queue_delete_selected(self):
        self.queue_tab.on_queue_delete_selected()

    def on_queue_clear_completed(self):
        self.queue_tab.on_queue_clear_completed()

    def on_queue_download_all(self):
        self.queue_tab.on_queue_download_all()

    def on_queue_download_selected(self):
        self.queue_tab.on_queue_download_selected()

    def on_queue_stop(self):
        self.queue_tab.on_queue_stop()

    def on_open_storage_folder(self):
        self.account_tab.on_open_storage_folder()

    def on_logout(self):
        self.account_tab.on_logout()

    def on_request_2fa_code(self):
        self.account_tab.on_request_2fa_code()

    def on_submit_login(self):
        self.account_tab.on_submit_login()
