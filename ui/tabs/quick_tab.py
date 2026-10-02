import os
import tkinter as tk
from tkinter import ttk, messagebox
from core.config import get_download_dir
from core.apple_api import download_ipa

class QuickTab:
    def __init__(self, app, notebook):
        self.app = app
        self.tab = ttk.Frame(notebook)
        notebook.add(self.tab, text="  تحميل سريع  ")
        self.build_ui()

    def build_ui(self):
        content = ttk.Frame(self.tab)
        content.pack(expand=True, fill=tk.BOTH, padx=30, pady=25)

        self.lbl_quick_status = ttk.Label(content, text="جاهز للتحميل", font=("Segoe UI", 11), anchor='center')
        self.lbl_quick_status.pack(fill=tk.X, pady=(15, 10))

        btn_box = ttk.Frame(content)
        btn_box.pack(pady=15)

        self.btn_quick_download = ttk.Button(
            btn_box,
            text="تحميل أحدث إصدار ⬇️",
            command=self.on_quick_download,
            style="Accent.TButton"
        )
        self.btn_quick_download.pack(side=tk.LEFT, padx=10, ipadx=15, ipady=5)

    def on_quick_download(self):
        if not self.app.current_app or not self.app.current_latest_ext_id:
            messagebox.showwarning("تنبيه", "الرجاء البحث عن تطبيق أولاً")
            return

        self.btn_quick_download.config(state=tk.DISABLED)
        ext_id = self.app.current_latest_ext_id
        bundle_id = self.app.current_app['bundle_id']
        app_name = "".join(c for c in self.app.current_app['name'] if c.isalnum() or c in (' ', '_', '-')).strip().replace(" ", "_")
        out_path = os.path.join(get_download_dir(), f"{app_name}_{ext_id}.ipa")

        self.app.log(f"بدء التحميل السريع للتطبيق {bundle_id} بإصدار {ext_id}...")
        self.app.run_in_thread(
            self._download_worker,
            bundle_id,
            ext_id,
            out_path,
            self.lbl_quick_status,
            self.btn_quick_download
        )

    def _download_worker(self, bundle_id, ext_id, out_path, status_label, enable_btn):
        def cb(msg):
            self.app.log(msg)
            self.app.root.after(0, lambda: status_label.config(text=msg[:60] + "..." if len(msg) > 60 else msg))

        success = download_ipa(bundle_id, ext_id, out_path, cb)

        if success:
            msg = f"تم التحميل بنجاح! ✅\nالمسار: {out_path}"
        else:
            msg = "فشل التحميل. راجع السجل للتفاصيل. ❌"

        self.app.root.after(0, lambda: status_label.config(text=msg))
        self.app.root.after(0, lambda: enable_btn.config(state=tk.NORMAL))
