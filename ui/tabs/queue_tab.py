import os
import tkinter as tk
from tkinter import ttk, messagebox
from core.config import get_download_dir
from core.queue_manager import (
    load_saved_queue,
    remove_from_saved_queue,
    update_saved_queue_item
)
from core.apple_api import generate_download_cmd, download_ipa

class QueueTab:
    def __init__(self, app, notebook):
        self.app = app
        self.tab = ttk.Frame(notebook)
        notebook.add(self.tab, text="  التحميلات المحفوظة 💾  ")

        self.queue_cancel_requested = False
        self.queue_in_progress = False

        self.build_ui()

    def build_ui(self):
        top_bar = ttk.Frame(self.tab, style="Alt.TFrame")
        top_bar.pack(fill=tk.X, padx=10, pady=(8, 6))

        self.btn_queue_download_sel = ttk.Button(
            top_bar,
            text="تحميل المحدد ⬇️",
            command=self.on_queue_download_selected,
            style="Success.TButton"
        )
        self.btn_queue_download_sel.pack(side=tk.RIGHT, padx=5, pady=6)

        self.btn_queue_download_all = ttk.Button(
            top_bar,
            text="تحميل الكل ⬇️⬇️",
            command=self.on_queue_download_all,
            style="Accent.TButton"
        )
        self.btn_queue_download_all.pack(side=tk.RIGHT, padx=5, pady=6)

        self.btn_queue_stop = ttk.Button(
            top_bar,
            text="إيقاف التحميل ⏹️",
            command=self.on_queue_stop,
            style="Danger.TButton",
            state=tk.DISABLED
        )
        self.btn_queue_stop.pack(side=tk.RIGHT, padx=5, pady=6)

        self.btn_queue_copy_cmd = ttk.Button(
            top_bar,
            text="نسخ أمر التحميل 📋",
            command=self.on_queue_copy_cmd
        )
        self.btn_queue_copy_cmd.pack(side=tk.RIGHT, padx=5, pady=6)

        self.btn_queue_delete = ttk.Button(
            top_bar,
            text="حذف من القائمة 🗑️",
            command=self.on_queue_delete_selected
        )
        self.btn_queue_delete.pack(side=tk.RIGHT, padx=5, pady=6)

        self.btn_queue_refresh = ttk.Button(
            top_bar,
            text="تحديث 🔄",
            command=self.refresh_saved_queue_ui
        )
        self.btn_queue_refresh.pack(side=tk.LEFT, padx=8, pady=6)

        self.btn_open_downloads = ttk.Button(
            top_bar,
            text="فتح مجلد التحميلات 📂",
            command=self.on_open_downloads_folder
        )
        self.btn_open_downloads.pack(side=tk.LEFT, padx=5, pady=6)

        self.lbl_queue_stats = ttk.Label(
            top_bar,
            text="",
            background=self.app.alt_bg,
            font=("Segoe UI", 10, "bold")
        )
        self.lbl_queue_stats.pack(side=tk.LEFT, padx=10, pady=6)

        tree_frame = ttk.Frame(self.tab)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 8))

        columns = ("status", "min_os", "version", "ext_id", "bundle_id", "app_name", "idx")
        self.queue_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="extended")

        self.queue_tree.heading("idx", text="#")
        self.queue_tree.heading("app_name", text="اسم التطبيق")
        self.queue_tree.heading("bundle_id", text="Bundle ID")
        self.queue_tree.heading("ext_id", text="معرف الإصدار (External ID)")
        self.queue_tree.heading("version", text="رقم الإصدار")
        self.queue_tree.heading("min_os", text="iOS المطلوب")
        self.queue_tree.heading("status", text="حالة التحميل")

        self.queue_tree.column("idx", width=40, anchor='center')
        self.queue_tree.column("app_name", width=140, anchor='e')
        self.queue_tree.column("bundle_id", width=190, anchor='center')
        self.queue_tree.column("ext_id", width=140, anchor='center')
        self.queue_tree.column("version", width=110, anchor='center')
        self.queue_tree.column("min_os", width=95, anchor='center')
        self.queue_tree.column("status", width=170, anchor='center')

        vsb_q = ttk.Scrollbar(tree_frame, orient="vertical", command=self.queue_tree.yview)
        self.queue_tree.configure(yscrollcommand=vsb_q.set)

        self.queue_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb_q.pack(side=tk.RIGHT, fill=tk.Y)

        self.queue_ctx_menu = tk.Menu(self.app.root, tearoff=0, bg=self.app.alt_bg, fg=self.app.fg_color)
        self.queue_ctx_menu.add_command(label="تحميل المحدد الآن ⬇️", command=self.on_queue_download_selected)
        self.queue_ctx_menu.add_command(label="نسخ أمر التحميل (CMD) 📋", command=self.on_queue_copy_cmd)
        self.queue_ctx_menu.add_separator()
        self.queue_ctx_menu.add_command(label="حذف من القائمة 🗑️", command=self.on_queue_delete_selected)
        self.queue_ctx_menu.add_command(label="مسح المكتمل فقط 🧹", command=self.on_queue_clear_completed)
        self.queue_ctx_menu.add_separator()
        self.queue_ctx_menu.add_command(label="فتح مجلد التحميلات 📂", command=self.on_open_downloads_folder)

        self.queue_tree.bind("<Button-3>", self.show_queue_context_menu)

    def show_queue_context_menu(self, event):
        item = self.queue_tree.identify_row(event.y)
        if item:
            if item not in self.queue_tree.selection():
                self.queue_tree.selection_set(item)
            self.queue_ctx_menu.post(event.x_root, event.y_root)

    def refresh_saved_queue_ui(self):
        for item in self.queue_tree.get_children():
            self.queue_tree.delete(item)

        items = load_saved_queue()
        completed = sum(1 for it in items if it.get('downloaded', False))
        total = len(items)
        pending = total - completed

        self.lbl_queue_stats.config(
            text=f"إجمالي المحفوظ: {total}  |  تم التحميل: {completed} ✅  |  في الانتظار: {pending} ⏳"
        )

        for i, it in enumerate(items):
            idx = i + 1
            item_id = it.get('id', '')
            status = it.get('status', 'في الانتظار ⏳')
            self.queue_tree.insert(
                "", "end", iid=item_id,
                values=(
                    status,
                    it.get('min_os', '?'),
                    it.get('version', '?'),
                    it.get('ext_id', ''),
                    it.get('bundle_id', ''),
                    it.get('app_name', ''),
                    idx
                )
            )

    def on_queue_copy_cmd(self):
        selected = self.queue_tree.selection()
        if not selected:
            messagebox.showinfo("تنبيه", "يرجى تحديد تطبيق واحد على الأقل من القائمة لنسخ أمره.")
            return

        items = load_saved_queue()
        id_to_item = {it.get('id'): it for it in items}

        cmds = []
        for s_id in selected:
            if s_id in id_to_item:
                it = id_to_item[s_id]
                cmd = generate_download_cmd(it['bundle_id'], it['ext_id'], it['app_name'], it.get('version', ''))
                cmds.append(cmd)

        full_cmd_text = "\n".join(cmds)
        self.app.copy_text_to_clipboard(full_cmd_text, f"تم نسخ أوامر التحميل لـ {len(cmds)} تطبيق بنجاح!")

    def on_queue_delete_selected(self):
        selected = self.queue_tree.selection()
        if not selected:
            messagebox.showinfo("تنبيه", "يرجى تحديد العناصر المراد حذفها من القائمة.")
            return

        if not messagebox.askyesno("تأكيد الحذف", f"هل أنت متأكد من حذف {len(selected)} عنصر من قائمة التحميلات المحفوظة؟"):
            return

        removed = remove_from_saved_queue(selected)
        self.app.log(f"تم حذف {removed} عنصر من قائمة التنزيل المحفوظة.")
        self.refresh_saved_queue_ui()

    def on_queue_clear_completed(self):
        items = load_saved_queue()
        completed_ids = [it.get('id') for it in items if it.get('downloaded', False)]
        if not completed_ids:
            messagebox.showinfo("تنبيه", "لا توجد عناصر مكتملة لحذفها.")
            return

        remove_from_saved_queue(completed_ids)
        self.app.log(f"تم مسح {len(completed_ids)} عنصر مكتمل من القائمة.")
        self.refresh_saved_queue_ui()

    def on_queue_download_all(self):
        items = load_saved_queue()
        if not items:
            messagebox.showinfo("تنبيه", "قائمة التحميلات المحفوظة فارغة.")
            return
        to_download = [it for it in items if not it.get('downloaded', False)]
        if not to_download:
            if messagebox.askyesno("تنبيه", "جميع العناصر محملة مسبقاً، هل تريد إعادة تحميل الكل؟"):
                to_download = items
            else:
                return

        self.start_queue_download_worker(to_download)

    def on_queue_download_selected(self):
        selected = self.queue_tree.selection()
        if not selected:
            messagebox.showinfo("تنبيه", "يرجى تحديد تطبيق أو عدة تطبيقات من القائمة للبدء بتحميلها.")
            return

        items = load_saved_queue()
        id_to_item = {it.get('id'): it for it in items}
        to_download = [id_to_item[s_id] for s_id in selected if s_id in id_to_item]

        self.start_queue_download_worker(to_download)

    def on_queue_stop(self):
        self.queue_cancel_requested = True
        self.app.log("تم طلب إيقاف تحميل القائمة...")

    def start_queue_download_worker(self, items_to_download):
        if self.queue_in_progress:
            messagebox.showinfo("تنبيه", "هناك عملية تحميل قيد التشغيل بالفعل.")
            return

        self.queue_in_progress = True
        self.queue_cancel_requested = False

        self.btn_queue_download_sel.config(state=tk.DISABLED)
        self.btn_queue_download_all.config(state=tk.DISABLED)
        self.btn_queue_stop.config(state=tk.NORMAL)

        self.app.log(f"بدء تحميل قائمة التنزيل لـ {len(items_to_download)} تطبيق...")
        self.app.run_in_thread(self._queue_worker, items_to_download)

    def on_open_downloads_folder(self):
        d = get_download_dir()
        try:
            os.startfile(d)
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذر فتح مجلد التحميلات: {str(e)}")

    def _queue_worker(self, items_to_download):
        for index, item in enumerate(items_to_download):
            if self.queue_cancel_requested:
                self.app.log("تم إيقاف التحميل بناءً على طلبك.")
                break

            item_id = item['id']
            app_name = item['app_name']
            ext_id = item['ext_id']
            bundle_id = item['bundle_id']
            ver_str = item.get('version', '')

            clean_name = "".join(c for c in app_name if c.isalnum() or c in (' ', '_', '-')).strip().replace(" ", "_")
            if not clean_name:
                clean_name = bundle_id
            ver_suffix = f"_{ver_str}" if ver_str and ver_str != "?" else f"_{ext_id}"
            out_path = os.path.join(get_download_dir(), f"{clean_name}{ver_suffix}.ipa")

            self.app.log(f"\n--- [{index + 1}/{len(items_to_download)}] بدء تحميل {app_name} (إصدار {ver_str}) ---")

            def mark_downloading(i_id=item_id):
                if self.queue_tree.exists(i_id):
                    self.queue_tree.set(i_id, "status", "جاري التحميل... ⏳")
            self.app.root.after(0, mark_downloading)

            update_saved_queue_item(item_id, status="جاري التحميل... ⏳")

            def cb(msg):
                self.app.log(msg)

            success = download_ipa(bundle_id, ext_id, out_path, cb)

            if success:
                new_status = "تم التحميل بنجاح ✅"
                update_saved_queue_item(item_id, status=new_status, downloaded=True, file_path=out_path)
                self.app.log(f"✅ اكتمل تحميل {app_name} بنجاح! المسار: {out_path}")
            else:
                new_status = "فشل التحميل ❌"
                update_saved_queue_item(item_id, status=new_status, downloaded=False)
                self.app.log(f"❌ فشل تحميل {app_name}.")

            def mark_result(i_id=item_id, st=new_status):
                if self.queue_tree.exists(i_id):
                    self.queue_tree.set(i_id, "status", st)
                self.refresh_saved_queue_ui()
            self.app.root.after(0, mark_result)

        def finish():
            self.queue_in_progress = False
            self.btn_queue_download_sel.config(state=tk.NORMAL)
            self.btn_queue_download_all.config(state=tk.NORMAL)
            self.btn_queue_stop.config(state=tk.DISABLED)
            msg = "اكتملت معالجة قائمة التحميل!" if not self.queue_cancel_requested else "توقف التحميل."
            self.app.log(msg)
            self.refresh_saved_queue_ui()

        self.app.root.after(0, finish)
