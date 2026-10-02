import os
import tkinter as tk
from tkinter import ttk, messagebox
from core.config import get_download_dir
from core.utils import setup_entry_clipboard, is_os_le
from core.queue_manager import add_to_saved_queue
from core.apple_api import get_all_version_ids, get_version_info, download_ipa, generate_download_cmd

class CompatibleTab:
    def __init__(self, app, notebook):
        self.app = app
        self.tab = ttk.Frame(notebook)
        notebook.add(self.tab, text="  البحث الذكي عن إصدار متوافق  ")
        self.compatible_match = None
        self.build_ui()

    def build_ui(self):
        content = ttk.Frame(self.tab)
        content.pack(expand=True, fill=tk.BOTH, padx=30, pady=25)

        input_frame = ttk.Frame(content)
        input_frame.pack(pady=15)

        self.entry_target_os = ttk.Entry(input_frame, justify='center', width=8, font=("Segoe UI", 12))
        self.entry_target_os.insert(0, "15.8")
        self.entry_target_os.pack(side=tk.LEFT, padx=10)
        setup_entry_clipboard(self.app.root, self.entry_target_os)

        ttk.Label(input_frame, text=":إصدار iOS المستهدف لجهازك", font=("Segoe UI", 12, "bold")).pack(side=tk.LEFT)

        self.btn_auto_search = ttk.Button(
            content,
            text="بحث ذكي تلقائي 🔍",
            command=self.on_auto_search,
            style="Accent.TButton"
        )
        self.btn_auto_search.pack(pady=10, ipadx=15, ipady=4)

        self.lbl_search_result = ttk.Label(content, text="", font=("Segoe UI", 11), justify='center')
        self.lbl_search_result.pack(pady=15)

        self.compat_btn_frame = ttk.Frame(content)
        self.compat_btn_frame.pack(pady=10)

        self.btn_download_compatible = ttk.Button(
            self.compat_btn_frame,
            text="تحميل هذا الإصدار المتوافق ⬇️",
            command=self.on_download_compatible,
            style="Accent.TButton"
        )
        self.btn_download_compatible.pack(side=tk.LEFT, padx=8, ipadx=12, ipady=4)

        self.btn_save_compatible = ttk.Button(
            self.compat_btn_frame,
            text="حفظ للتحميل لاحقاً 💾",
            command=self.on_save_compatible_to_queue
        )
        self.btn_save_compatible.pack(side=tk.LEFT, padx=8, ipadx=12, ipady=4)

        self.btn_copy_compatible_cmd = ttk.Button(
            self.compat_btn_frame,
            text="نسخ أمر التحميل (CMD) 📋",
            command=self.on_copy_compatible_cmd
        )
        self.btn_copy_compatible_cmd.pack(side=tk.LEFT, padx=8, ipadx=12, ipady=4)

        self.compat_btn_frame.pack_forget()

    def clear(self):
        self.lbl_search_result.config(text="")
        self.compat_btn_frame.pack_forget()
        self.compatible_match = None

    def on_auto_search(self):
        if not self.app.current_app or not self.app.current_latest_ext_id:
            messagebox.showwarning("تنبيه", "الرجاء البحث عن تطبيق أولاً")
            return

        target_os = self.entry_target_os.get().strip()
        if not target_os:
            return

        self.btn_auto_search.config(state=tk.DISABLED)
        self.compat_btn_frame.pack_forget()
        self.lbl_search_result.config(text="جاري البحث الذكي...")
        self.app.log(f"بدء البحث الذكي عن إصدار متوافق مع iOS {target_os}...")

        self.app.run_in_thread(self._auto_search_worker, target_os)

    def _auto_search_worker(self, target_os):
        app_id = self.app.current_app['app_id']

        versions = self.app.current_versions
        if not versions:
            self.app.log("جاري جلب قائمة الإصدارات أولاً...")
            versions = get_all_version_ids(app_id, self.app.current_latest_ext_id)
            if versions:
                self.app.current_versions = versions

        if not versions:
            self.app.root.after(0, lambda: self.lbl_search_result.config(text="فشل جلب قائمة الإصدارات من خادم أبل."))
            self.app.root.after(0, lambda: self.btn_auto_search.config(state=tk.NORMAL))
            return

        # Check latest version first
        latest_ext = str(versions[-1])
        self.app.log(f"فحص أحدث إصدار متاح أولاً (ID: {latest_ext})...")
        latest_info = get_version_info(app_id, latest_ext)

        if latest_info and is_os_le(latest_info['minOS'], target_os):
            self.app.log(f"أحدث إصدار متوافق بالفعل مع جهازك! (iOS {latest_info['minOS']})")
            self._show_compatible_result(latest_info)
            return

        self.app.log(f"أحدث إصدار يتطلب نظاماً أحدث. جاري البحث بين {len(versions)} إصدار تاريخي...")

        low = 0
        high = len(versions) - 1
        best_match = None
        step_count = 0

        while low <= high:
            step_count += 1
            mid = (low + high) // 2
            ext_id = str(versions[mid])
            self.app.log(f"خطوة {step_count}: فحص الإصدار {mid + 1}/{len(versions)} (ID: {ext_id})...")

            info = get_version_info(app_id, ext_id)
            if not info:
                self.app.log(f"تنبيه: تعذر قراءة الإصدار {ext_id}، جاري اختبار إصدار مجاور...")
                for offset in [-1, 1, -2, 2]:
                    adj_idx = mid + offset
                    if 0 <= adj_idx < len(versions):
                        adj_info = get_version_info(app_id, str(versions[adj_idx]))
                        if adj_info:
                            info = adj_info
                            mid = adj_idx
                            break

                if not info:
                    high = mid - 1
                    continue

            self.app.log(f"نتيجة الفحص: إصدار {info['displayVersion']} يتطلب iOS {info['minOS']}")

            if is_os_le(info['minOS'], target_os):
                best_match = info
                low = mid + 1
            else:
                high = mid - 1

        if best_match:
            self._show_compatible_result(best_match)
        else:
            self.app.log("لم يتم العثور على إصدار متوافق.")
            self.app.root.after(0, lambda: self.lbl_search_result.config(text="عذراً، لم يتم العثور على أي إصدار متوافق مع نظامك."))
            self.app.root.after(0, lambda: self.btn_auto_search.config(state=tk.NORMAL))

    def _show_compatible_result(self, match):
        res_text = (
            f"🎉 تم العثور على أنسب وأحدث إصدار متوافق بنجاح!\n\n"
            f"اسم الإصدار: {match['displayVersion']}   |   أقل iOS مطلوب: {match['minOS']}\n"
            f"معرف الإصدار (External ID): {match['externalId']}"
        )
        self.app.log(f"تم العثور على الإصدار المتوافق: {match['displayVersion']} (ID: {match['externalId']})")
        self.compatible_match = match

        self.app.root.after(0, lambda: self.lbl_search_result.config(text=res_text))
        self.app.root.after(0, lambda: self.compat_btn_frame.pack(pady=10))
        self.app.root.after(0, lambda: self.btn_auto_search.config(state=tk.NORMAL))

    def on_download_compatible(self):
        if not self.compatible_match:
            return

        match = self.compatible_match
        ext_id = match['externalId']
        ver_str = match['displayVersion']
        bundle_id = self.app.current_app['bundle_id']
        app_name = "".join(c for c in self.app.current_app['name'] if c.isalnum() or c in (' ', '_', '-')).strip().replace(" ", "_")
        out_path = os.path.join(get_download_dir(), f"{app_name}_{ver_str}.ipa")

        self.btn_download_compatible.config(state=tk.DISABLED)
        self.app.log(f"بدء تحميل الإصدار المتوافق {ver_str}...")

        def cb(msg):
            self.app.log(msg)

        def worker():
            success = download_ipa(bundle_id, ext_id, out_path, cb)
            msg = "اكتمل تحميل الإصدار المتوافق بنجاح! ✅" if success else "فشل تحميل الإصدار المتوافق. ❌"
            self.app.log(msg)
            self.app.root.after(0, lambda: self.lbl_search_result.config(text=msg + f"\nالمسار: {out_path}"))
            self.app.root.after(0, lambda: self.btn_download_compatible.config(state=tk.NORMAL))

        self.app.run_in_thread(worker)

    def on_save_compatible_to_queue(self):
        if not self.compatible_match:
            return
        match = self.compatible_match
        app = self.app.current_app
        ok, msg = add_to_saved_queue(
            app_name=app['name'],
            bundle_id=app['bundle_id'],
            app_id=app['app_id'],
            ext_id=match['externalId'],
            version=match['displayVersion'],
            min_os=match['minOS']
        )
        self.app.log(msg)
        if hasattr(self.app, 'queue_tab'):
            self.app.queue_tab.refresh_saved_queue_ui()
        messagebox.showinfo("قائمة التنزيل المحفوظة", msg)

    def on_copy_compatible_cmd(self):
        if not self.compatible_match:
            return
        match = self.compatible_match
        app = self.app.current_app
        cmd = generate_download_cmd(app['bundle_id'], match['externalId'], app['name'], match['displayVersion'])
        self.app.copy_text_to_clipboard(cmd, f"تم نسخ أمر تحميل الإصدار المتوافق {match['displayVersion']}")
