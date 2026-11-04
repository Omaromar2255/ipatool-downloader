import os
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from core.config import (
    BASE_DIR,
    IPATOOL_DIR,
    IPATOOL_PATH,
    SETTINGS,
    get_keychain_passphrase,
    save_settings,
    get_download_dir,
    set_download_dir,
    DEFAULT_DOWNLOAD_DIR
)
from core.apple_api import (
    validate_email_format,
    InteractiveLoginSession,
    check_auth_status,
    perform_login,
    perform_revoke
)
from core.utils import setup_entry_clipboard

class AccountTab:
    def __init__(self, app, notebook):
        self.app = app
        self.tab = ttk.Frame(notebook)
        notebook.add(self.tab, text="  الحساب وتسجيل الدخول 👤  ")
        self.pass_visible = False
        self.active_session = None
        self.build_ui()

    def build_ui(self):
        canvas = tk.Canvas(self.tab, bg=self.app.bg_color, highlightthickness=0)
        vscroll = ttk.Scrollbar(self.tab, orient="vertical", command=canvas.yview)
        scroll_content = ttk.Frame(canvas)

        scroll_content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_content, anchor="nw", width=1010)
        canvas.configure(yscrollcommand=vscroll.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=10)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y, pady=10)

        # =========================================================
        # Card 1: Current Account Status & Storage Info
        # =========================================================
        card_status = ttk.Frame(scroll_content, style="Alt.TFrame")
        card_status.pack(fill=tk.X, padx=15, pady=(5, 12))

        ttk.Label(
            card_status,
            text="حالة الحساب ومكان حفظ الجلسة 🔐",
            style="Title.TLabel",
            anchor='e'
        ).pack(fill=tk.X, padx=15, pady=(12, 6))

        self.lbl_acc_status_badge = ttk.Label(
            card_status,
            text="جاري فحص حالة الحساب...",
            font=("Segoe UI", 11, "bold"),
            anchor='e'
        )
        self.lbl_acc_status_badge.pack(fill=tk.X, padx=15, pady=2)

        self.lbl_acc_name_email = ttk.Label(card_status, text="", font=("Segoe UI", 10), anchor='e')
        self.lbl_acc_name_email.pack(fill=tk.X, padx=15, pady=2)

        desc_storage = (
            f"📁 مكان تخزين بيانات الحساب والجلسة:\n"
            f"   • المسار: {IPATOOL_DIR}\n"
            f"   • الحماية: بيانات الدخول مشفرة بالرمز المؤقت للحافظة (الحالي: {get_keychain_passphrase()})"
        )
        self.lbl_desc_storage = ttk.Label(card_status, text=desc_storage, style="Sub.TLabel", justify='right', anchor='e')
        self.lbl_desc_storage.pack(fill=tk.X, padx=15, pady=(4, 10))

        status_btns = ttk.Frame(card_status, style="Alt.TFrame")
        status_btns.pack(fill=tk.X, padx=15, pady=(0, 12))

        self.btn_refresh_acc = ttk.Button(status_btns, text="تحديث حالة الحساب 🔄", command=self.refresh_account_status_ui)
        self.btn_refresh_acc.pack(side=tk.RIGHT, padx=5)

        self.btn_open_storage = ttk.Button(status_btns, text="فتح مجلد تخزين الحساب 📂", command=self.on_open_storage_folder)
        self.btn_open_storage.pack(side=tk.RIGHT, padx=5)

        self.btn_logout = ttk.Button(status_btns, text="تسجيل الخروج 🚪", command=self.on_logout, style="Danger.TButton")
        self.btn_logout.pack(side=tk.RIGHT, padx=5)

        # =========================================================
        # Card 1.5: Download Directory Settings
        # =========================================================
        card_download = ttk.Frame(scroll_content, style="Alt.TFrame")
        card_download.pack(fill=tk.X, padx=15, pady=(0, 12))

        ttk.Label(
            card_download,
            text="مجلد حفظ وتنزيل التطبيقات (Downloads Folder) 📥",
            style="Title.TLabel",
            anchor='e'
        ).pack(fill=tk.X, padx=15, pady=(12, 6))

        self.lbl_download_dir_path = ttk.Label(
            card_download,
            text=f"📁 المسار: {get_download_dir()}",
            font=("Segoe UI", 9, "bold"),
            anchor='e'
        )
        self.lbl_download_dir_path.pack(fill=tk.X, padx=15, pady=3)

        ttk.Label(
            card_download,
            text="يتم تحميل جميع ملفات الـ IPA تلقائياً إلى هذا المجلد، وهو مستثنى تماماً من رفعه إلى GitHub مع مجلد الكاش (.cache).",
            style="Sub.TLabel",
            justify='right',
            anchor='e'
        ).pack(fill=tk.X, padx=15, pady=(2, 8))

        dl_btns = ttk.Frame(card_download, style="Alt.TFrame")
        dl_btns.pack(fill=tk.X, padx=15, pady=(0, 12))

        self.btn_open_downloads = ttk.Button(
            dl_btns,
            text="فتح مجلد التحميلات 📂",
            command=self.on_open_downloads_folder
        )
        self.btn_open_downloads.pack(side=tk.RIGHT, padx=5)

        self.btn_change_downloads = ttk.Button(
            dl_btns,
            text="تغيير المجلد 📁",
            command=self.on_change_downloads_folder
        )
        self.btn_change_downloads.pack(side=tk.RIGHT, padx=5)

        self.btn_reset_downloads = ttk.Button(
            dl_btns,
            text="استعادة الافتراضي 🔄",
            command=self.on_reset_downloads_folder
        )
        self.btn_reset_downloads.pack(side=tk.RIGHT, padx=5)

        # =========================================================
        # Card 2: Interactive CMD Login (Recommended)
        # =========================================================
        card_cmd = ttk.Frame(scroll_content, style="Alt.TFrame")
        card_cmd.pack(fill=tk.X, padx=15, pady=(0, 12))

        ttk.Label(
            card_cmd,
            text="الطريقة الأولى (موصى بها): تسجيل الدخول التفاعلي عبر نافذة الأوامر CMD 💻",
            style="Title.TLabel",
            anchor='e'
        ).pack(fill=tk.X, padx=15, pady=(12, 6))

        cmd_desc = (
            "يفتح نافذة سطر أوامر تفاعلية تسير معك مرحلة بمرحلة:\n"
            "1. البريد الإلكتروني والتحقق من صحته ⬅️ 2. كلمة المرور والتأكد من قبول أبل لها\n"
            "3. انتظار وصول كود التحقق بخطوتين (2FA) وفحصه ⬅️ 4. الرمز المؤقت للحافظة وتأكيد نجاح الدخول.\n"
            "وبعد الانتهاء بنجاح يتم تحديث حالة الحساب تلقائياً داخل هذا البرنامج فور إغلاق النافذة."
        )
        ttk.Label(card_cmd, text=cmd_desc, style="Sub.TLabel", justify='right', anchor='e').pack(fill=tk.X, padx=15, pady=(0, 10))

        cmd_btn_box = ttk.Frame(card_cmd, style="Alt.TFrame")
        cmd_btn_box.pack(fill=tk.X, padx=15, pady=(0, 12))

        self.btn_open_cmd_login = ttk.Button(
            cmd_btn_box,
            text="⚡ فتح نافذة CMD التفاعلية خطوة بخطوة 🚀",
            command=self.on_open_interactive_login,
            style="Accent.TButton"
        )
        self.btn_open_cmd_login.pack(side=tk.RIGHT, padx=5, ipadx=15, ipady=6)

        # =========================================================
        # Card 3: Interactive Staged GUI Login (4 Consecutive Stages)
        # =========================================================
        card_login = ttk.Frame(scroll_content, style="Alt.TFrame")
        card_login.pack(fill=tk.X, padx=15, pady=(0, 15))

        header_row = ttk.Frame(card_login, style="Alt.TFrame")
        header_row.pack(fill=tk.X, padx=15, pady=(12, 4))

        ttk.Label(
            header_row,
            text="الطريقة الثانية: تسجيل الدخول التفاعلي على مراحل متتالية في الواجهة 🔑",
            style="Title.TLabel",
            anchor='e'
        ).pack(side=tk.RIGHT)

        self.btn_reset_wizard = ttk.Button(
            header_row,
            text="إعادة البدء من المرحلة 1 ↺",
            command=self.reset_wizard
        )
        self.btn_reset_wizard.pack(side=tk.LEFT, padx=5)

        # Live Status Banner
        self.lbl_login_feedback = ttk.Label(
            card_login,
            text="ابدأ بالمرحلة 1: اكتب بريد أبل (Apple ID) واضغط زر التحقق من البريد.",
            font=("Segoe UI", 10, "bold"),
            anchor='e',
            justify='right',
            foreground=self.app.accent_color,
            background=self.app.alt_bg
        )
        self.lbl_login_feedback.pack(fill=tk.X, padx=20, pady=(4, 8))

        # --- Stage 1: Email Verification ---
        self.step1_box = ttk.LabelFrame(card_login, text=" المرحلة 1️⃣ : إدخال البريد الإلكتروني والتحقق من صحته ", padding=10)
        self.step1_box.pack(fill=tk.X, padx=15, pady=6)

        row1 = ttk.Frame(self.step1_box)
        row1.pack(fill=tk.X)

        ttk.Label(row1, text="بريد أبل (Apple ID):", style="Header.TLabel").pack(side=tk.RIGHT, padx=(10, 5))
        self.entry_login_email = ttk.Entry(row1, width=36, font=("Segoe UI", 10), justify='left')
        self.entry_login_email.pack(side=tk.RIGHT, padx=5)
        self.entry_login_email.bind("<Return>", lambda e: self.on_step1_verify_email())
        setup_entry_clipboard(self.app.root, self.entry_login_email)

        self.btn_verify_email = ttk.Button(
            row1,
            text="التحقق من البريد ⬅️",
            command=self.on_step1_verify_email,
            style="Accent.TButton"
        )
        self.btn_verify_email.pack(side=tk.RIGHT, padx=8, ipadx=8)

        self.lbl_step1_status = ttk.Label(row1, text="", font=("Segoe UI", 9, "bold"))
        self.lbl_step1_status.pack(side=tk.RIGHT, padx=5)

        # --- Stage 2: Password & Apple Login Check ---
        self.step2_box = ttk.LabelFrame(card_login, text=" المرحلة 2️⃣ : إدخال كلمة المرور والتأكد من تسجيل الدخول لدى أبل ", padding=10)
        self.step2_box.pack(fill=tk.X, padx=15, pady=6)

        row2 = ttk.Frame(self.step2_box)
        row2.pack(fill=tk.X)

        ttk.Label(row2, text="كلمة المرور:", style="Header.TLabel").pack(side=tk.RIGHT, padx=(10, 5))

        self.entry_login_pass = ttk.Entry(row2, width=30, font=("Segoe UI", 10), show="*", justify='left', state=tk.DISABLED)
        self.entry_login_pass.pack(side=tk.RIGHT, padx=5)
        self.entry_login_pass.bind("<Return>", lambda e: self.on_request_2fa_code())
        setup_entry_clipboard(self.app.root, self.entry_login_pass)

        def toggle_pass_vis():
            self.pass_visible = not self.pass_visible
            self.entry_login_pass.config(show="" if self.pass_visible else "*")
            self.btn_show_pass.config(text="🙈" if self.pass_visible else "👁️")

        self.btn_show_pass = ttk.Button(row2, text="👁️", width=3, command=toggle_pass_vis, state=tk.DISABLED)
        self.btn_show_pass.pack(side=tk.RIGHT, padx=2)

        self.btn_send_2fa = ttk.Button(
            row2,
            text="تأكد من الحساب واطلب كود التحقق 📱",
            command=self.on_request_2fa_code,
            style="Accent.TButton",
            state=tk.DISABLED
        )
        self.btn_send_2fa.pack(side=tk.RIGHT, padx=8, ipadx=8)

        self.lbl_step2_status = ttk.Label(row2, text="(بانتظار إتمام المرحلة 1)", style="Sub.TLabel")
        self.lbl_step2_status.pack(side=tk.RIGHT, padx=5)

        # --- Stage 3: Wait for & Verify 2FA Code ---
        self.step3_box = ttk.LabelFrame(card_login, text=" المرحلة 3️⃣ : انتظار وصول كود التحقق (2FA) والتأكد من صحته ", padding=10)
        self.step3_box.pack(fill=tk.X, padx=15, pady=6)

        row3 = ttk.Frame(self.step3_box)
        row3.pack(fill=tk.X)

        ttk.Label(row3, text="كود التحقق (6 أرقام):", style="Header.TLabel").pack(side=tk.RIGHT, padx=(10, 5))
        self.entry_login_2fa = ttk.Entry(row3, width=14, font=("Segoe UI", 12, "bold"), justify='center', state=tk.DISABLED)
        self.entry_login_2fa.pack(side=tk.RIGHT, padx=5)
        self.entry_login_2fa.bind("<Return>", lambda e: self.on_step3_verify_2fa())
        setup_entry_clipboard(self.app.root, self.entry_login_2fa)

        self.btn_verify_2fa = ttk.Button(
            row3,
            text="تأكيد كود التحقق ✅",
            command=self.on_step3_verify_2fa,
            style="Accent.TButton",
            state=tk.DISABLED
        )
        self.btn_verify_2fa.pack(side=tk.RIGHT, padx=8, ipadx=8)

        self.btn_resend_2fa = ttk.Button(
            row3,
            text="تأخر الكود؟ إعادة إرسال 🔄",
            command=self.on_request_2fa_code,
            state=tk.DISABLED
        )
        self.btn_resend_2fa.pack(side=tk.RIGHT, padx=4)

        self.lbl_step3_status = ttk.Label(row3, text="(بانتظار التحقق من كلمة المرور في المرحلة 2)", style="Sub.TLabel")
        self.lbl_step3_status.pack(side=tk.RIGHT, padx=5)

        # --- Stage 4: Temporary Keychain Passphrase ---
        self.step4_box = ttk.LabelFrame(card_login, text=" المرحلة 4️⃣ : إدخال الرمز المؤقت للحافظة وتأكيد تسجيل الدخول ", padding=10)
        self.step4_box.pack(fill=tk.X, padx=15, pady=(6, 15))

        row4 = ttk.Frame(self.step4_box)
        row4.pack(fill=tk.X)

        ttk.Label(row4, text="الرمز المؤقت للحافظة:", style="Header.TLabel").pack(side=tk.RIGHT, padx=(10, 5))
        self.entry_login_keychain = ttk.Entry(row4, width=14, font=("Segoe UI", 11, "bold"), justify='center')
        self.entry_login_keychain.pack(side=tk.RIGHT, padx=5)
        self.entry_login_keychain.insert(0, get_keychain_passphrase())
        self.entry_login_keychain.config(state=tk.DISABLED)
        self.entry_login_keychain.bind("<Return>", lambda e: self.on_submit_login())
        setup_entry_clipboard(self.app.root, self.entry_login_keychain)

        self.btn_submit_login = ttk.Button(
            row4,
            text="حفظ الرمز وتأكيد الدخول نهائياً 🔐",
            command=self.on_submit_login,
            style="Success.TButton",
            state=tk.DISABLED
        )
        self.btn_submit_login.pack(side=tk.RIGHT, padx=8, ipadx=10)

        self.lbl_step4_status = ttk.Label(row4, text="(يُطلب بعد التأكد من صحة كود التحقق)", style="Sub.TLabel")
        self.lbl_step4_status.pack(side=tk.RIGHT, padx=5)

    # =========================================================
    # Staged Logic (Stage 1 -> Stage 2 -> Stage 3 -> Stage 4)
    # =========================================================

    def reset_wizard(self):
        if self.active_session:
            self.active_session.close()
            self.active_session = None

        self.entry_login_email.config(state=tk.NORMAL)
        self.btn_verify_email.config(state=tk.NORMAL)
        self.lbl_step1_status.config(text="")

        self.entry_login_pass.config(state=tk.NORMAL)
        self.entry_login_pass.delete(0, tk.END)
        self.entry_login_pass.config(state=tk.DISABLED)
        self.btn_show_pass.config(state=tk.DISABLED)
        self.btn_send_2fa.config(state=tk.DISABLED)
        self.lbl_step2_status.config(text="(بانتظار إتمام المرحلة 1)", foreground=self.app.fg_color)

        self.entry_login_2fa.config(state=tk.NORMAL)
        self.entry_login_2fa.delete(0, tk.END)
        self.entry_login_2fa.config(state=tk.DISABLED)
        self.btn_verify_2fa.config(state=tk.DISABLED)
        self.btn_resend_2fa.config(state=tk.DISABLED)
        self.lbl_step3_status.config(text="(بانتظار التحقق من كلمة المرور في المرحلة 2)", foreground=self.app.fg_color)

        self.entry_login_keychain.config(state=tk.NORMAL)
        self.entry_login_keychain.delete(0, tk.END)
        self.entry_login_keychain.insert(0, get_keychain_passphrase())
        self.entry_login_keychain.config(state=tk.DISABLED)
        self.btn_submit_login.config(state=tk.DISABLED)
        self.lbl_step4_status.config(text="(يُطلب بعد التأكد من صحة كود التحقق)", foreground=self.app.fg_color)

        self.lbl_login_feedback.config(
            text="ابدأ بالمرحلة 1: اكتب بريد أبل (Apple ID) واضغط زر التحقق من البريد.",
            foreground=self.app.accent_color
        )
        self.entry_login_email.focus_set()

    def on_step1_verify_email(self):
        email = self.entry_login_email.get().strip()
        ok, msg = validate_email_format(email)
        if not ok:
            self.lbl_step1_status.config(text="❌ بريد غير صالح", foreground=self.app.danger_color)
            self.lbl_login_feedback.config(text=f"❌ {msg}", foreground=self.app.danger_color)
            messagebox.showerror("خطأ في البريد الإلكتروني", msg)
            self.entry_login_email.focus_set()
            return

        self.lbl_step1_status.config(text="✅ البريد صحيح", foreground=self.app.success_color)
        self.lbl_login_feedback.config(
            text="✅ المرحلة 1 مكتملة بنجاح! انتقل الآن للمرحلة 2: أدخل كلمة المرور واضغط على زر فحص الحساب.",
            foreground=self.app.success_color
        )
        self.app.log(f"المرحلة 1: تم التحقق من صحة صيغة البريد الإلكتروني ({email}).")

        # Enable Stage 2
        self.entry_login_pass.config(state=tk.NORMAL)
        self.btn_show_pass.config(state=tk.NORMAL)
        self.btn_send_2fa.config(state=tk.NORMAL)
        self.lbl_step2_status.config(text="👈 أدخل كلمة المرور واضغط زر الفحص", foreground=self.app.accent_color)
        self.entry_login_pass.focus_set()

    def on_request_2fa_code(self):
        email = self.entry_login_email.get().strip()
        ok_email, msg_email = validate_email_format(email)
        if not ok_email:
            self.on_step1_verify_email()
            return

        pwd = self.entry_login_pass.get().strip()
        if not pwd:
            messagebox.showerror("كلمة المرور مطلوبة", "يرجى كتابة كلمة مرور حساب أبل أولاً.")
            self.entry_login_pass.focus_set()
            return

        if self.active_session:
            self.active_session.close()

        self.btn_verify_email.config(state=tk.DISABLED)
        self.btn_send_2fa.config(state=tk.DISABLED)
        self.btn_verify_2fa.config(state=tk.DISABLED)
        self.btn_resend_2fa.config(state=tk.DISABLED)

        self.lbl_step2_status.config(text="⏳ جاري فحص الحساب لدى أبل...", foreground=self.app.accent_color)
        self.lbl_login_feedback.config(
            text="⏳ جاري الاتصال بخوادم أبل للتحقق من البريد وكلمة المرور... (قد يستغرق 10-30 ثانية، يرجى الانتظار)",
            foreground=self.app.accent_color
        )
        self.app.log(f"المرحلة 2: جاري التحقق من البريد وكلمة المرور لـ {email} مع خوادم أبل...")

        def log_cb(line):
            self.app.log(f"ipatool: {line}")

        self.active_session = InteractiveLoginSession(
            email=email,
            password=pwd,
            temp_passphrase=get_keychain_passphrase(),
            log_callback=log_cb
        )

        def worker():
            status, msg, data = self.active_session.verify_credentials_and_wait_2fa()

            def update():
                self.btn_verify_email.config(state=tk.NORMAL)
                self.btn_send_2fa.config(state=tk.NORMAL)

                if status == "ERROR":
                    self.lbl_step2_status.config(text="❌ كلمة المرور أو الحساب غير صحيح", foreground=self.app.danger_color)
                    self.lbl_login_feedback.config(text=f"❌ {msg}", foreground=self.app.danger_color)
                    self.app.log(f"❌ خطأ في المرحلة 2: {msg}")
                    messagebox.showerror("فشل التحقق من كلمة المرور", f"رفضت خوادم أبل بيانات الدخول:\n\n{msg}")
                    self.entry_login_pass.focus_set()

                elif status == "SUCCESS":
                    self.lbl_step2_status.config(text="✅ الحساب صحيح وتم تسجيل الدخول!", foreground=self.app.success_color)
                    self.lbl_step3_status.config(text="✅ لم يتطلب كود تحقق إضافي", foreground=self.app.success_color)
                    self.lbl_login_feedback.config(
                        text="✅ تم التأكد من الحساب بنجاح! انتقل للمرحلة 4 لإدخال الرمز المؤقت للحافظة واضغط حفظ.",
                        foreground=self.app.success_color
                    )
                    self._enable_step4()

                elif status == "NEEDS_2FA":
                    self.lbl_step2_status.config(text="✅ كلمة المرور صحيحة تماماً", foreground=self.app.success_color)
                    self.lbl_step3_status.config(
                        text="⏳ الجلسة مفتوحة وتنتظر إدخال الكود (خذ وقتك حتى لو تأخر)",
                        foreground="#f9e2af"
                    )
                    self.lbl_login_feedback.config(
                        text="📱 تم التأكد من صحة الإيميل والباسورد وإرسال كود التحقق لجهازك! الجلسة مفتوحة وتنتظرك، اكتب الكود في المرحلة 3.",
                        foreground="#f9e2af"
                    )
                    self.entry_login_2fa.config(state=tk.NORMAL)
                    self.entry_login_2fa.delete(0, tk.END)
                    self.btn_verify_2fa.config(state=tk.NORMAL)
                    self.btn_resend_2fa.config(state=tk.NORMAL)
                    self.entry_login_2fa.focus_set()
                    self.app.log("✅ تم التأكد من صحة البريد وكلمة المرور! الجلسة مفتوحة وبانتظار كود 2FA.")

            self.app.root.after(0, update)

        self.app.run_in_thread(worker)

    def on_step3_verify_2fa(self):
        if not self.active_session:
            messagebox.showwarning("تنبيه", "يرجى إتمام المرحلة 2 أولاً للتحقق من كلمة المرور.")
            return

        code = self.entry_login_2fa.get().strip().replace(" ", "").replace("-", "")
        if not (code.isdigit() and len(code) == 6):
            messagebox.showerror("كود غير صالح", "يرجى كتابة كود التحقق المكون من 6 أرقام صحيحة.")
            self.entry_login_2fa.focus_set()
            return

        self.btn_verify_2fa.config(state=tk.DISABLED)
        self.btn_resend_2fa.config(state=tk.DISABLED)
        self.btn_send_2fa.config(state=tk.DISABLED)
        self.lbl_step3_status.config(text="⏳ جاري التحقق من صحة الكود لدى أبل...", foreground=self.app.accent_color)
        self.lbl_login_feedback.config(
            text=f"⏳ جاري فحص كود التحقق ({code}) مع خوادم أبل...",
            foreground=self.app.accent_color
        )
        self.app.log(f"المرحلة 3: فحص كود التحقق ({code}) مع خوادم أبل...")

        def worker():
            ok, msg, data = self.active_session.submit_2fa_code(code)

            def update():
                self.btn_send_2fa.config(state=tk.NORMAL)
                self.btn_resend_2fa.config(state=tk.NORMAL)

                if ok:
                    self.lbl_step3_status.config(text="✅ تم التأكد من صحة كود التحقق!", foreground=self.app.success_color)
                    self.entry_login_2fa.config(state=tk.DISABLED)
                    self.btn_verify_2fa.config(state=tk.DISABLED)
                    self.btn_resend_2fa.config(state=tk.DISABLED)
                    self.lbl_login_feedback.config(
                        text="✅ تم التأكد من صحة كود التحقق ونجاح الدخول! الآن في المرحلة 4 أدخل الرمز المؤقت للحافظة واضغط حفظ.",
                        foreground=self.app.success_color
                    )
                    self.app.log(f"✅ المرحلة 3 مكتملة: {msg}")
                    self._enable_step4()
                else:
                    self.btn_verify_2fa.config(state=tk.NORMAL)
                    self.lbl_step3_status.config(text="❌ الكود غير صحيح أو انتهى", foreground=self.app.danger_color)
                    self.lbl_login_feedback.config(
                        text=f"❌ كود التحقق غير صحيح: {msg} — يمكنك تصحيح الكود أو الضغط على 'إعادة إرسال 🔄'.",
                        foreground=self.app.danger_color
                    )
                    self.app.log(f"❌ خطأ في كود التحقق: {msg}")
                    messagebox.showerror(
                        "كود التحقق غير صحيح",
                        f"لم تقبل أبل كود التحقق:\n{msg}\n\n"
                        "يرجى التأكد من كتابة الكود الصحيح، أو الضغط على 'تأخر الكود؟ إعادة إرسال 🔄'."
                    )

            self.app.root.after(0, update)

        self.app.run_in_thread(worker)

    def _enable_step4(self):
        self.entry_login_keychain.config(state=tk.NORMAL)
        if not self.entry_login_keychain.get().strip():
            self.entry_login_keychain.insert(0, get_keychain_passphrase())
        self.btn_submit_login.config(state=tk.NORMAL)
        self.lbl_step4_status.config(
            text="👈 أدخل الرمز المؤقت (افتراضي 2211) واضغط حفظ",
            foreground=self.app.accent_color
        )
        self.entry_login_keychain.focus_set()
        self.entry_login_keychain.selection_range(0, tk.END)

    def on_submit_login(self):
        # Stage 4: Finalize temporary keychain passphrase and verify session
        passphrase = self.entry_login_keychain.get().strip()
        if not passphrase:
            passphrase = "2211"
            self.entry_login_keychain.insert(0, "2211")

        if not self.active_session:
            email = self.entry_login_email.get().strip()
            pwd = self.entry_login_pass.get().strip()
            auth_code = self.entry_login_2fa.get().strip()
            if not email or not pwd:
                messagebox.showerror("تنبيه", "يرجى البدء بالمرحلة 1 والمرحلة 2 أولاً.")
                return
            self.active_session = InteractiveLoginSession(email, pwd, temp_passphrase=passphrase)

        self.btn_submit_login.config(state=tk.DISABLED)
        self.lbl_step4_status.config(text="⏳ جاري حفظ وتشفير الجلسة بالرمز المؤقت...", foreground=self.app.accent_color)
        self.lbl_login_feedback.config(
            text="⏳ جاري حفظ وتشفير الجلسة بالرمز المؤقت والتأكد النهائي من حالة الحساب...",
            foreground=self.app.accent_color
        )

        def worker():
            ok, msg, info = self.active_session.finalize_keychain_passphrase(passphrase)
            self.active_session.close()

            def update():
                self.btn_submit_login.config(state=tk.NORMAL)
                self.lbl_desc_storage.config(
                    text=(
                        f"📁 مكان تخزين بيانات الحساب والجلسة:\n"
                        f"   • المسار: {IPATOOL_DIR}\n"
                        f"   • الحماية: بيانات الدخول مشفرة بالرمز المؤقت للحافظة (الحالي: {passphrase})"
                    )
                )
                self.refresh_account_status_ui()

                if ok and info.get("logged_in"):
                    self.lbl_step4_status.config(text="✅ تم حفظ الجلسة بنجاح!", foreground=self.app.success_color)
                    self.lbl_login_feedback.config(
                        text=f"🎉 تم تسجيل الدخول بنجاح تام! الحساب: {info.get('name')} ({info.get('email')}) | الرمز: {passphrase}",
                        foreground=self.app.success_color
                    )
                    self.app.log(f"🎉 تم تسجيل الدخول بنجاح تام: {info.get('name')} ({info.get('email')}) | الرمز: {passphrase}")
                    messagebox.showinfo(
                        "تم تسجيل الدخول بنجاح ✅",
                        f"🎉 تم التأكد من تسجيل الدخول وحفظ الجلسة بنجاح!\n\n"
                        f"👤 الاسم: {info.get('name')}\n"
                        f"📧 البريد: {info.get('email')}\n"
                        f"🔑 الرمز المؤقت للحافظة: {passphrase}\n\n"
                        f"أنت الآن جاهز لتحميل وشراء التطبيقات."
                    )
                else:
                    self.lbl_step4_status.config(text="❌ تعذر تأكيد الجلسة", foreground=self.app.danger_color)
                    self.lbl_login_feedback.config(text=f"❌ {msg}", foreground=self.app.danger_color)
                    messagebox.showerror("خطأ", f"تعذر تأكيد حفظ الجلسة:\n{msg}")

            self.app.root.after(0, update)

        self.app.run_in_thread(worker)

    # =========================================================
    # Interactive CMD Launcher
    # =========================================================

    def on_open_interactive_login(self):
        bat_path = os.path.join(BASE_DIR, "login.bat")
        script_path = os.path.join(BASE_DIR, "interactive_login.py")
        try:
            if os.path.exists(bat_path):
                cmd_str = f'start /wait "" "{bat_path}"'
            elif os.path.exists(script_path):
                cmd_str = f'start /wait cmd /c python "{script_path}"'
            else:
                cmd_str = f'start /wait cmd /k "title تسجيل الدخول بحساب أبل & "{IPATOOL_PATH}" auth login"'

            self.app.log("💻 تم فتح نافذة CMD التفاعلية لتسجيل الدخول مرحلة بمرحلة...")
            self.lbl_login_feedback.config(
                text="💻 نافذة CMD التفاعلية مفتوحة الآن... أكمل المراحل بداخلها وسيتم تحديث حالة الحساب تلقائياً فور إغلاقها.",
                foreground=self.app.accent_color
            )

            def wait_cmd_worker():
                proc = subprocess.Popen(cmd_str, shell=True)
                proc.wait()
                from core.config import load_settings
                new_settings = load_settings()
                SETTINGS.update(new_settings)
                self.app.root.after(0, self._on_cmd_login_finished)

            self.app.run_in_thread(wait_cmd_worker)
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذر فتح نافذة CMD: {str(e)}")

    def _on_cmd_login_finished(self):
        passphrase = get_keychain_passphrase()
        self.lbl_desc_storage.config(
            text=(
                f"📁 مكان تخزين بيانات الحساب والجلسة:\n"
                f"   • المسار: {IPATOOL_DIR}\n"
                f"   • الحماية: بيانات الدخول مشفرة بالرمز المؤقت للحافظة (الحالي: {passphrase})"
            )
        )
        info = check_auth_status(passphrase)
        self.refresh_account_status_ui()
        if info.get("logged_in"):
            self.lbl_login_feedback.config(
                text=f"✅ تم تسجيل الدخول بنجاح عبر CMD! الحساب النشط: {info['name']} ({info['email']})",
                foreground=self.app.success_color
            )

    # =========================================================
    # Download Directory Settings
    # =========================================================

    def on_open_downloads_folder(self):
        d = get_download_dir()
        try:
            os.startfile(d)
            self.app.log(f"تم فتح مجلد التحميلات: {d}")
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذر فتح مجلد التحميلات: {str(e)}")

    def on_change_downloads_folder(self):
        chosen = filedialog.askdirectory(
            title="اختر مجلد حفظ التطبيقات (IPA)",
            initialdir=get_download_dir()
        )
        if chosen:
            new_path = set_download_dir(chosen)
            self.lbl_download_dir_path.config(text=f"📁 المسار: {new_path}")
            self.app.log(f"تم تغيير مسار حفظ التطبيقات إلى: {new_path}")
            messagebox.showinfo("تم التغيير", f"تم اعتماد مجلد التنزيل الجديد:\n{new_path}")

    def on_reset_downloads_folder(self):
        new_path = set_download_dir(DEFAULT_DOWNLOAD_DIR)
        self.lbl_download_dir_path.config(text=f"📁 المسار: {new_path}")
        self.app.log(f"تمت استعادة مجلد التنزيل الافتراضي: {new_path}")
        messagebox.showinfo("تمت الاستعادة", f"تمت استعادة مجلد التنزيل الافتراضي بنجاح:\n{new_path}")

    # =========================================================
    # Account Status & Revoke
    # =========================================================

    def refresh_account_status_ui(self):
        self.lbl_acc_status_badge.config(text="جاري التحقق من بيانات الحساب...")
        self.app.run_in_thread(self._check_account_worker)

    def _check_account_worker(self):
        passphrase = get_keychain_passphrase()
        info = check_auth_status(passphrase)

        def update():
            if info['logged_in']:
                self.lbl_acc_status_badge.config(text="الحالة: مسجل الدخول بنجاح ✅", foreground=self.app.success_color)
                self.lbl_acc_name_email.config(text=f"الاسم: {info['name']}   |   الحساب: {info['email']}   |   الرمز المؤقت: {passphrase}")
                self.app.log(f"الحساب متصل: {info['name']} ({info['email']})")
            else:
                self.lbl_acc_status_badge.config(text="الحالة: غير مسجل الدخول أو بحاجة لتجديد الاعتماد ❌", foreground=self.app.danger_color)
                self.lbl_acc_name_email.config(text="يرجى تسجيل الدخول عبر نافذة CMD أو المراحل الـ 4 بالأسفل")
                self.app.log("الحساب غير متصل حالياً.")

        self.app.root.after(0, update)

    def on_open_storage_folder(self):
        try:
            if not os.path.exists(IPATOOL_DIR):
                os.makedirs(IPATOOL_DIR, exist_ok=True)
            os.startfile(IPATOOL_DIR)
            self.app.log(f"تم فتح مجلد تخزين الحساب: {IPATOOL_DIR}")
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذر فتح المجلد: {str(e)}")

    def on_logout(self):
        if not messagebox.askyesno("تسجيل الخروج", "هل أنت متأكد من تسجيل الخروج وإلغاء الاعتماد من متجر أبل؟"):
            return
        passphrase = get_keychain_passphrase()
        self.app.log("جاري تسجيل الخروج...")
        self.app.run_in_thread(self._logout_worker, passphrase)

    def _logout_worker(self, passphrase):
        ok, msg = perform_revoke(passphrase)
        self.app.log(msg)
        self.app.root.after(0, lambda: messagebox.showinfo("تسجيل الخروج", msg))
        self.app.root.after(0, self.refresh_account_status_ui)
