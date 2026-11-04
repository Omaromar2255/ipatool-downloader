import os
import tkinter as tk
from tkinter import ttk, messagebox
import concurrent.futures
from core.config import get_download_dir
from core.cache import get_cached_version
from core.queue_manager import add_to_saved_queue
from core.apple_api import get_all_version_ids, get_version_info, download_ipa, generate_download_cmd
from core.utils import setup_entry_clipboard

class VersionsTab:
    def __init__(self, app, notebook):
        self.app = app
        self.tab = ttk.Frame(notebook)
        notebook.add(self.tab, text="  استعراض وفحص الإصدارات  ")

        self.scan_cancel_requested = False
        self.scan_in_progress = False

        self.build_ui()

    def build_ui(self):
        top_ctrl = ttk.Frame(self.tab)
        top_ctrl.pack(fill=tk.X, padx=10, pady=(8, 4))

        self.btn_load_versions = ttk.Button(
            top_ctrl,
            text="تحميل قائمة الإصدارات 🔄",
            command=self.on_load_versions,
            style="Accent.TButton"
        )
        self.btn_load_versions.pack(side=tk.RIGHT, padx=5)

        self.lbl_versions_count = ttk.Label(top_ctrl, text="", style="Header.TLabel")
        self.lbl_versions_count.pack(side=tk.RIGHT, padx=15)

        # Batch Scan Controls Frame
        scan_ctrl = ttk.Frame(self.tab, style="Alt.TFrame")
        scan_ctrl.pack(fill=tk.X, padx=10, pady=5)

        f_top_n = ttk.Frame(scan_ctrl, style="Alt.TFrame")
        f_top_n.pack(side=tk.RIGHT, padx=8, pady=5)

        self.btn_scan_top_n = ttk.Button(f_top_n, text="فحص أحدث الإصدارات ⚡", command=self.on_scan_top_n)
        self.btn_scan_top_n.pack(side=tk.RIGHT, padx=4)

        self.entry_top_n = ttk.Entry(f_top_n, width=4, justify='center')
        self.entry_top_n.insert(0, "15")
        self.entry_top_n.pack(side=tk.RIGHT, padx=2)
        setup_entry_clipboard(self.app.root, self.entry_top_n)

        ttk.Label(f_top_n, text=":عدد", background=self.app.alt_bg).pack(side=tk.RIGHT, padx=2)

        f_range = ttk.Frame(scan_ctrl, style="Alt.TFrame")
        f_range.pack(side=tk.RIGHT, padx=12, pady=5)

        self.btn_scan_range = ttk.Button(f_range, text="فحص النطاق 🎯", command=self.on_scan_range)
        self.btn_scan_range.pack(side=tk.RIGHT, padx=4)

        self.entry_range_to = ttk.Entry(f_range, width=5, justify='center')
        self.entry_range_to.insert(0, "")
        self.entry_range_to.pack(side=tk.RIGHT, padx=2)
        setup_entry_clipboard(self.app.root, self.entry_range_to)

        ttk.Label(f_range, text="إلى #:", background=self.app.alt_bg).pack(side=tk.RIGHT, padx=2)

        self.entry_range_from = ttk.Entry(f_range, width=5, justify='center')
        self.entry_range_from.insert(0, "")
        self.entry_range_from.pack(side=tk.RIGHT, padx=2)
        setup_entry_clipboard(self.app.root, self.entry_range_from)

        ttk.Label(f_range, text="من #:", background=self.app.alt_bg).pack(side=tk.RIGHT, padx=2)

        self.btn_cancel_scan = ttk.Button(
            scan_ctrl,
            text="إلغاء ⏹️",
            command=self.on_cancel_scan,
            style="Danger.TButton",
            state=tk.DISABLED
        )
        self.btn_cancel_scan.pack(side=tk.LEFT, padx=10, pady=5)

        self.scan_prog_bar = ttk.Progressbar(
            scan_ctrl,
            orient="horizontal",
            mode="determinate",
            length=120,
            style="Horizontal.TProgressbar"
        )
        self.scan_prog_bar.pack(side=tk.LEFT, padx=5, pady=5)

        self.lbl_scan_status = ttk.Label(scan_ctrl, text="", background=self.app.alt_bg)
        self.lbl_scan_status.pack(side=tk.LEFT, padx=5)

        # Treeview for Versions
        tree_frame = ttk.Frame(self.tab)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 8))

        columns = ("status", "min_os", "version", "ext_id", "idx")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")

        self.tree.heading("idx", text="# (الرقم)")
        self.tree.heading("ext_id", text="معرف الإصدار (External ID)")
        self.tree.heading("version", text="رقم الإصدار")
        self.tree.heading("min_os", text="أقل iOS مطلوب")
        self.tree.heading("status", text="الحالة")

        self.tree.column("idx", width=65, anchor='center')
        self.tree.column("ext_id", width=175, anchor='center')
        self.tree.column("version", width=140, anchor='center')
        self.tree.column("min_os", width=115, anchor='center')
        self.tree.column("status", width=220, anchor='center')

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.ctx_menu = tk.Menu(self.app.root, tearoff=0, bg=self.app.alt_bg, fg=self.app.fg_color)
        self.ctx_menu.add_command(label="فحص التوافق لهذا الإصدار 🔍", command=self.on_check_compatibility)
        self.ctx_menu.add_command(label="تحميل هذا الإصدار الآن ⬇️", command=self.on_download_selected)
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command(label="حفظ هذا الإصدار للتحميل لاحقاً 💾", command=self.on_save_selected_to_queue)
        self.ctx_menu.add_command(label="نسخ أمر التحميل (CMD) 📋", command=self.on_copy_selected_cmd)

        self.tree.bind("<Button-3>", self.show_context_menu)

    def show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.ctx_menu.post(event.x_root, event.y_root)

    def clear(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.lbl_versions_count.config(text="")
        self.entry_range_from.delete(0, tk.END)
        self.entry_range_to.delete(0, tk.END)

    def on_load_versions(self):
        if not self.app.current_app or not self.app.current_latest_ext_id:
            messagebox.showwarning("تنبيه", "الرجاء البحث عن تطبيق أولاً")
            return

        self.btn_load_versions.config(state=tk.DISABLED)
        self.app.log("جاري جلب قائمة الإصدارات من خوادم أبل...")
        self.app.run_in_thread(self._load_versions_worker)

    def _load_versions_worker(self):
        app_id = self.app.current_app['app_id']
        latest_ext_id = self.app.current_latest_ext_id

        versions, err_msg = get_all_version_ids(app_id, latest_ext_id, return_error=True)

        if not versions:
            msg = f"> لم يتم العثور على إصدارات: {err_msg}" if err_msg else "> لم يتم العثور على إصدارات أو حدث خطأ في الاتصال بخوادم أبل."
            self.app.log(msg)
            self.app.root.after(0, lambda: self.btn_load_versions.config(state=tk.NORMAL))
            return

        self.app.current_versions = versions
        self.app.log(f"تم جلب {len(versions)} إصدار بنجاح.")

        def update_ui():
            for item in self.tree.get_children():
                self.tree.delete(item)

            cached_count = 0
            for i, v in enumerate(reversed(versions)):
                idx = len(versions) - i
                vid_str = str(v)
                marker = " ← أحدث" if vid_str == str(latest_ext_id) else ""

                cached = get_cached_version(app_id, vid_str)
                if cached:
                    cached_count += 1
                    status = "محفوظ محلياً ⚡"
                    ver_str = cached.get('displayVersion', '?')
                    min_os = cached.get('minOS', '?')
                else:
                    status = f"-{marker}"
                    ver_str = "?"
                    min_os = "?"

                self.tree.insert("", "end", iid=vid_str, values=(status, min_os, ver_str, vid_str, idx))

            self.lbl_versions_count.config(text=f"إجمالي الإصدارات: {len(versions)} (المحفوظ: {cached_count})")
            self.btn_load_versions.config(state=tk.NORMAL)

            self.entry_range_from.delete(0, tk.END)
            self.entry_range_from.insert(0, str(len(versions)))
            self.entry_range_to.delete(0, tk.END)
            self.entry_range_to.insert(0, str(max(1, len(versions) - 20)))

        self.app.root.after(0, update_ui)

    def on_check_compatibility(self):
        selected = self.tree.selection()
        if not selected:
            return

        item = selected[0]
        ext_id = self.tree.item(item, "values")[3]
        app_id = self.app.current_app['app_id']

        self.app.log(f"جاري فحص توافق الإصدار {ext_id}...")
        self.tree.set(item, "status", "جاري الفحص...")
        self.app.run_in_thread(self._check_single_worker, app_id, ext_id, item)

    def _check_single_worker(self, app_id, ext_id, tree_item):
        info = get_version_info(app_id, ext_id)
        if info:
            self.app.log(f"نتيجة {ext_id}: إصدار {info['displayVersion']} (iOS {info['minOS']})")
            def update():
                self.tree.set(tree_item, "min_os", info['minOS'])
                self.tree.set(tree_item, "version", info['displayVersion'])
                self.tree.set(tree_item, "status", "تم الفحص ✅")
            self.app.root.after(0, update)
        else:
            self.app.log(f"فشل فحص الإصدار {ext_id}")
            self.app.root.after(0, lambda: self.tree.set(tree_item, "status", "فشل الفحص ❌"))

    def on_download_selected(self):
        selected = self.tree.selection()
        if not selected:
            return

        item = selected[0]
        ext_id = self.tree.item(item, "values")[3]
        ver_str = self.tree.item(item, "values")[2]
        bundle_id = self.app.current_app['bundle_id']

        clean_name = "".join(c for c in self.app.current_app['name'] if c.isalnum() or c in (' ', '_', '-')).strip().replace(" ", "_")
        ver_suffix = f"_{ver_str}" if ver_str and ver_str != "?" else f"_{ext_id}"
        out_path = os.path.join(get_download_dir(), f"{clean_name}{ver_suffix}.ipa")

        self.app.log(f"بدء تحميل الإصدار {ext_id}...")
        self.tree.set(item, "status", "جاري التحميل...")

        def cb(msg):
            self.app.log(msg)
            self.app.root.after(0, lambda: self.tree.set(item, "status", "تحميل..."))

        def worker():
            success = download_ipa(bundle_id, ext_id, out_path, cb)
            msg = "اكتمل التحميل ✅" if success else "فشل التحميل ❌"
            self.app.root.after(0, lambda: self.tree.set(item, "status", msg))

        self.app.run_in_thread(worker)

    def on_save_selected_to_queue(self):
        selected = self.tree.selection()
        if not selected:
            return

        item = selected[0]
        vals = self.tree.item(item, "values")
        ext_id = vals[3]
        ver_str = vals[2]
        min_os = vals[1]

        app = self.app.current_app
        ok, msg = add_to_saved_queue(
            app_name=app['name'],
            bundle_id=app['bundle_id'],
            app_id=app['app_id'],
            ext_id=ext_id,
            version=ver_str,
            min_os=min_os
        )
        self.app.log(msg)
        if hasattr(self.app, 'queue_tab'):
            self.app.queue_tab.refresh_saved_queue_ui()
        messagebox.showinfo("قائمة التنزيل المحفوظة", msg)

    def on_copy_selected_cmd(self):
        selected = self.tree.selection()
        if not selected:
            return

        item = selected[0]
        vals = self.tree.item(item, "values")
        ext_id = vals[3]
        ver_str = vals[2]

        app = self.app.current_app
        cmd = generate_download_cmd(app['bundle_id'], ext_id, app['name'], ver_str)
        self.app.copy_text_to_clipboard(cmd, f"تم نسخ أمر تحميل الإصدار {ext_id}")

    # --- Batch Parallel Scanning ---

    def on_scan_top_n(self):
        if not self.app.current_versions:
            messagebox.showwarning("تنبيه", "يرجى تحميل قائمة الإصدارات أولاً")
            return

        try:
            n = int(self.entry_top_n.get().strip())
            if n <= 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("خطأ", "يرجى إدخال عدد صحيح موجب (مثلاً 15 أو 20)")
            return

        top_vids = list(reversed(self.app.current_versions))[:n]
        self.start_batch_scan(top_vids)

    def on_scan_range(self):
        if not self.app.current_versions:
            messagebox.showwarning("تنبيه", "يرجى تحميل قائمة الإصدارات أولاً")
            return

        try:
            f = int(self.entry_range_from.get().strip())
            t = int(self.entry_range_to.get().strip())
        except ValueError:
            messagebox.showerror("خطأ", "يرجى إدخال أرقام صحيحة لنطاق الفهرس")
            return

        total = len(self.app.current_versions)
        start_idx = min(f, t)
        end_idx = max(f, t)

        start_idx = max(1, start_idx)
        end_idx = min(total, end_idx)

        selected_vids = []
        for idx in range(end_idx, start_idx - 1, -1):
            selected_vids.append(self.app.current_versions[idx - 1])

        self.start_batch_scan(selected_vids)

    def start_batch_scan(self, vids_to_scan):
        if self.scan_in_progress:
            messagebox.showinfo("تنبيه", "هناك عملية فحص قيد التشغيل بالفعل.")
            return

        self.scan_in_progress = True
        self.scan_cancel_requested = False

        self.btn_scan_top_n.config(state=tk.DISABLED)
        self.btn_scan_range.config(state=tk.DISABLED)
        self.btn_cancel_scan.config(state=tk.NORMAL)

        self.scan_prog_bar['value'] = 0
        self.scan_prog_bar['maximum'] = len(vids_to_scan)

        self.app.log(f"بدء الفحص المتوازي لـ {len(vids_to_scan)} إصدار...")
        self.app.run_in_thread(self._batch_scan_worker, vids_to_scan)

    def on_cancel_scan(self):
        self.scan_cancel_requested = True
        self.lbl_scan_status.config(text="جاري الإلغاء...")
        self.app.log("تم طلب إلغاء الفحص...")

    def _batch_scan_worker(self, vids_to_scan):
        app_id = self.app.current_app['app_id']
        total = len(vids_to_scan)
        completed = 0

        def mark_pending():
            for vid in vids_to_scan:
                vid_str = str(vid)
                if self.tree.exists(vid_str):
                    curr_status = self.tree.item(vid_str, "values")[0]
                    if "محفوظ" not in curr_status:
                        self.tree.set(vid_str, "status", "في الانتظار...")
        self.app.root.after(0, mark_pending)

        def scan_single(vid):
            if self.scan_cancel_requested:
                return vid, None
            vid_str = str(vid)
            self.app.root.after(0, lambda: self.tree.set(vid_str, "status", "جاري الفحص...") if self.tree.exists(vid_str) else None)
            info = get_version_info(app_id, vid_str)
            return vid, info

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(scan_single, vid) for vid in vids_to_scan]

            for future in concurrent.futures.as_completed(futures):
                if self.scan_cancel_requested:
                    break

                try:
                    vid, info = future.result()
                    vid_str = str(vid)
                    completed += 1

                    def update_row(v=vid_str, inf=info, c=completed):
                        if self.tree.exists(v):
                            if inf:
                                self.tree.set(v, "min_os", inf['minOS'])
                                self.tree.set(v, "version", inf['displayVersion'])
                                self.tree.set(v, "status", "تم الفحص ✅")
                            else:
                                self.tree.set(v, "status", "فشل الفحص ❌")
                        self.scan_prog_bar['value'] = c
                        self.lbl_scan_status.config(text=f"{c}/{total}")

                    self.app.root.after(0, update_row)
                except Exception as e:
                    self.app.log(f"خطأ أثناء فحص إصدار: {str(e)}")

        def finish():
            self.scan_in_progress = False
            self.btn_scan_top_n.config(state=tk.NORMAL)
            self.btn_scan_range.config(state=tk.NORMAL)
            self.btn_cancel_scan.config(state=tk.DISABLED)
            msg = "تم الانتهاء من الفحص بنجاح!" if not self.scan_cancel_requested else "تم إلغاء الفحص."
            self.lbl_scan_status.config(text=msg)
            self.app.log(msg)

        self.app.root.after(0, finish)
