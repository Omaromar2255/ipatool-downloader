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
from core.apple_api import check_auth_status, perform_login, perform_revoke
from core.utils import setup_entry_clipboard

class AccountTab:
    def __init__(self, app, notebook):
        self.app = app
        self.tab = ttk.Frame(notebook)
        notebook.add(self.tab, text="  الحساب وتسجيل الدخول 👤  ")
        self.pass_visible = False
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
            f"   • الحماية: بيانات الدخول مشفرة بباسورد الحافظة (افتراضي: {get_keychain_passphrase()})"
        )
        ttk.Label(card_status, text=desc_storage, style="Sub.TLabel", justify='right', anchor='e').pack(fill=tk.X, padx=15, pady=(4, 10))

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
            text="الطريقة الأولى (الأسرع والأضمن): تسجيل الدخول التفاعلي عبر نافذة الأوامر 💻",
            style="Title.TLabel",
            anchor='e'
        ).pack(fill=tk.X, padx=15, pady=(12, 6))

        cmd_desc = (
            "تفتح نافذة سطر أوامر تفاعلية تسألك بالترتيب تماماً كما اعتدت في السي ام دي:\n"
            "1. البريد الإلكتروني ⬅️ 2. كلمة المرور ⬅️ 3. كود التحقق بخطوتين (2FA) ⬅️ 4. باسورد الحافظة (2211)\n"
            "وبعد الانتهاء بنجاح يتم تحديث حالة الحساب تلقائياً داخل هذا البرنامج."
        )
        ttk.Label(card_cmd, text=cmd_desc, style="Sub.TLabel", justify='right', anchor='e').pack(fill=tk.X, padx=15, pady=(0, 10))

        cmd_btn_box = ttk.Frame(card_cmd, style="Alt.TFrame")
        cmd_btn_box.pack(fill=tk.X, padx=15, pady=(0, 12))

        self.btn_open_cmd_login = ttk.Button(
            cmd_btn_box,
            text="⚡ فتح نافذة CMD التفاعلية لتسجيل الدخول 🚀",
            command=self.on_open_interactive_login,
            style="Accent.TButton"
        )
        self.btn_open_cmd_login.pack(side=tk.RIGHT, padx=5, ipadx=15, ipady=6)

        # =========================================================
        # Card 3: Two-Stage GUI Login
        # =========================================================
        card_login = ttk.Frame(scroll_content, style="Alt.TFrame")
        card_login.pack(fill=tk.X, padx=15, pady=(0, 15))

        ttk.Label(
            card_login,
            text="الطريقة الثانية: تسجيل الدخول المنظم على مرحلتين من الواجهة 🔑",
            style="Title.TLabel",
            anchor='e'
        ).pack(fill=tk.X, padx=15, pady=(12, 6))

        # --- Step 1 Frame ---
        step1_box = ttk.LabelFrame(card_login, text=" المرحلة 1: بيانات الحساب الأساسية وطلب رمز التحقق ", padding=10)
        step1_box.pack(fill=tk.X, padx=15, pady=8)

        grid1 = ttk.Frame(step1_box)
        grid1.pack(fill=tk.X, pady=5)

        ttk.Label(grid1, text="بريد أبل (Apple ID):", style="Header.TLabel").grid(row=0, column=2, sticky='e', padx=10, pady=6)
        self.entry_login_email = ttk.Entry(grid1, width=38, font=("Segoe UI", 10), justify='left')
        self.entry_login_email.grid(row=0, column=1, sticky='w', padx=5, pady=6)
        setup_entry_clipboard(self.app.root, self.entry_login_email)

        ttk.Label(grid1, text="كلمة المرور:", style="Header.TLabel").grid(row=1, column=2, sticky='e', padx=10, pady=6)
        f_pass = ttk.Frame(grid1)
        f_pass.grid(row=1, column=1, sticky='w', padx=5, pady=6)

        self.entry_login_pass = ttk.Entry(f_pass, width=30, font=("Segoe UI", 10), show="*", justify='left')
        self.entry_login_pass.pack(side=tk.LEFT)
        setup_entry_clipboard(self.app.root, self.entry_login_pass)

        def toggle_pass_vis():
            self.pass_visible = not self.pass_visible
            self.entry_login_pass.config(show="" if self.pass_visible else "*")
            btn_show_pass.config(text="🙈" if self.pass_visible else "👁️")

        btn_show_pass = ttk.Button(f_pass, text="👁️", width=3, command=toggle_pass_vis)
        btn_show_pass.pack(side=tk.LEFT, padx=4)

        self.btn_send_2fa = ttk.Button(
            step1_box,
            text="1️⃣ إرسال البيانات وطلب رمز التحقق للايفون (2FA) 📱",
            command=self.on_request_2fa_code,
            style="Accent.TButton"
        )
        self.btn_send_2fa.pack(pady=10, ipadx=12, ipady=4)

        # --- Step 2 Frame ---
        step2_box = ttk.LabelFrame(card_login, text=" المرحلة 2: إدخال رمز التحقق وباسورد الحافظة 🔐 ", padding=10)
        step2_box.pack(fill=tk.X, padx=15, pady=8)

        grid2 = ttk.Frame(step2_box)
        grid2.pack(fill=tk.X, pady=5)

        ttk.Label(grid2, text="رمز التحقق (2FA Code):", style="Header.TLabel").grid(row=0, column=2, sticky='e', padx=10, pady=6)
        self.entry_login_2fa = ttk.Entry(grid2, width=16, font=("Segoe UI", 12, "bold"), justify='center')
        self.entry_login_2fa.grid(row=0, column=1, sticky='w', padx=5, pady=6)
        setup_entry_clipboard(self.app.root, self.entry_login_2fa)
        ttk.Label(grid2, text="(اكتب الـ 6 أرقام التي ظهرت على شاشة هاتفك الايفون)", style="Sub.TLabel").grid(row=0, column=0, sticky='w', padx=5, pady=6)

        ttk.Label(grid2, text="باسورد الحافظة (Keychain):", style="Header.TLabel").grid(row=1, column=2, sticky='e', padx=10, pady=6)
        self.entry_login_keychain = ttk.Entry(grid2, width=16, font=("Segoe UI", 10), justify='center')
        self.entry_login_keychain.grid(row=1, column=1, sticky='w', padx=5, pady=6)
        self.entry_login_keychain.insert(0, get_keychain_passphrase())
        setup_entry_clipboard(self.app.root, self.entry_login_keychain)
        ttk.Label(grid2, text="(كلمة مرور محلية لتشفير الجلسة، مثلاً 2211)", style="Sub.TLabel").grid(row=1, column=0, sticky='w', padx=5, pady=6)

        self.btn_submit_login = ttk.Button(
            step2_box,
            text="2️⃣ تأكيد الرمز وإتمام تسجيل الدخول 🔐",
            command=self.on_submit_login,
            style="Success.TButton"
        )
        self.btn_submit_login.pack(pady=10, ipadx=15, ipady=4)

        # Status feedback label
        self.lbl_login_feedback = ttk.Label(
            card_login,
            text="",
            font=("Segoe UI", 10, "bold"),
            anchor='center',
            background=self.app.alt_bg
        )
        self.lbl_login_feedback.pack(fill=tk.X, padx=20, pady=(0, 15))

    # --- Actions ---

    def on_open_interactive_login(self):
        bat_path = os.path.join(BASE_DIR, "login.bat")
        try:
            if os.path.exists(bat_path):
                subprocess.Popen(f'start "" "{bat_path}"', shell=True)
            else:
                subprocess.Popen(f'start cmd /k "title تسجيل الدخول بحساب أبل & "{IPATOOL_PATH}" auth login"', shell=True)

            self.app.log("تم تشغيل نافذة CMD التفاعلية لتسجيل الدخول...")
            messagebox.showinfo(
                "تسجيل الدخول التفاعلي عبر CMD",
                "تم فتح نافذة الأوامر السوداء (CMD).\n\n"
                "اتبع الخطوات داخل النافذة:\n"
                "1. اكتب الإيميل ثم Enter\n"
                "2. اكتب كلمة المرور ثم Enter\n"
                "3. اكتب كود 2FA الواصل للايفون ثم Enter\n"
                "4. اكتب باسورد الحافظة (مثل 2211) ثم Enter\n\n"
                "بعد الانتهاء وإغلاق النافذة، اضغط على زر 'تحديث حالة الحساب 🔄' بالأعلى."
            )
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذر فتح نافذة CMD: {str(e)}")

    def refresh_account_status_ui(self):
        self.lbl_acc_status_badge.config(text="جاري التحقق من بيانات الحساب...")
        self.app.run_in_thread(self._check_account_worker)

    def _check_account_worker(self):
        passphrase = get_keychain_passphrase()
        info = check_auth_status(passphrase)

        def update():
            if info['logged_in']:
                self.lbl_acc_status_badge.config(text="الحالة: مسجل الدخول بنجاح ✅", foreground=self.app.success_color)
                self.lbl_acc_name_email.config(text=f"الاسم: {info['name']}   |   الحساب: {info['email']}   |   باسورد الحافظة: {passphrase}")
                self.app.log(f"الحساب متصل: {info['name']} ({info['email']})")
            else:
                self.lbl_acc_status_badge.config(text="الحالة: غير مسجل الدخول أو بحاجة لتجديد الاعتماد ❌", foreground=self.app.danger_color)
                self.lbl_acc_name_email.config(text="يرجى تسجيل الدخول بأحد الطرق الموضحة بالأسفل")
                self.app.log("الحساب غير متصل حالياً.")

        self.app.root.after(0, update)

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

    def on_request_2fa_code(self):
        email = self.entry_login_email.get().strip()
        pwd = self.entry_login_pass.get().strip()
        passphrase = self.entry_login_keychain.get().strip()

        if not email or not pwd:
            messagebox.showerror("بيانات ناقصة", "يرجى كتابة البريد الإلكتروني وكلمة المرور أولاً.")
            return

        if not passphrase:
            passphrase = "2211"
            self.entry_login_keychain.insert(0, "2211")

        self.lbl_login_feedback.config(
            text="جاري الاتصال بخوادم أبل للتحقق من البيانات وإرسال الكود للايفون... قد يستغرق لحظات ⏳",
            foreground=self.app.accent_color
        )
        self.btn_send_2fa.config(state=tk.DISABLED)
        self.btn_submit_login.config(state=tk.DISABLED)
        self.app.log(f"المرحلة 1: فحص بيانات الحساب وطلب كود 2FA لـ {email}...")

        def log_cb(msg):
            self.app.log(f"ipatool: {msg}")

        def worker():
            ok, msg, data = perform_login(email, pwd, passphrase, auth_code=None, log_callback=log_cb)
            def update():
                self.btn_send_2fa.config(state=tk.NORMAL)
                self.btn_submit_login.config(state=tk.NORMAL)

                if ok:
                    self.lbl_login_feedback.config(text="تم تسجيل الدخول بنجاح دون الحاجة لرمز! ✅", foreground=self.app.success_color)
                    SETTINGS['keychain_passphrase'] = passphrase
                    save_settings(SETTINGS)
                    self.refresh_account_status_ui()
                    messagebox.showinfo("نجاح", "تم تسجيل الدخول بنجاح!")
                else:
                    self.lbl_login_feedback.config(
                        text="📱 تم إرسال الرمز لجهاز الايفون! اكتب الرمز في حقل 'رمز التحقق (2FA)' بالأسفل ثم اضغط زر التأكيد.",
                        foreground="#f9e2af"
                    )
                    self.entry_login_2fa.focus_set()
                    self.app.log(f"استجابة أبل: {msg}")
                    messagebox.showinfo(
                        "رمز التحقق 📱",
                        "إذا كانت بيانات الحساب صحيحة، فقد وصلك إشعار وكود مكون من 6 أرقام على جهاز الايفون.\n\n"
                        "يرجى كتابة الرمز في خانة 'المرحلة 2' ثم الضغط على زر '2️⃣ تأكيد الرمز وإتمام تسجيل الدخول'."
                    )

            self.app.root.after(0, update)

        self.app.run_in_thread(worker)

    def on_submit_login(self):
        email = self.entry_login_email.get().strip()
        pwd = self.entry_login_pass.get().strip()
        passphrase = self.entry_login_keychain.get().strip()
        auth_code = self.entry_login_2fa.get().strip()

        if not email or not pwd:
            messagebox.showerror("بيانات ناقصة", "يرجى التأكد من كتابة البريد وكلمة المرور.")
            return

        if not auth_code:
            messagebox.showerror("رمز التحقق مطلوب", "يرجى كتابة رمز التحقق المكون من 6 أرقام الواصل لهاتفك.")
            self.entry_login_2fa.focus_set()
            return

        if not passphrase:
            passphrase = "2211"
            self.entry_login_keychain.insert(0, "2211")

        self.lbl_login_feedback.config(text="جاري توثيق تسجيل الدخول برمز التحقق وباسورد الحافظة...", foreground=self.app.accent_color)
        self.btn_submit_login.config(state=tk.DISABLED)
        self.btn_send_2fa.config(state=tk.DISABLED)
        self.app.log(f"المرحلة 2: إرسال كود 2FA ({auth_code}) مع باسورد الحافظة ({passphrase})...")

        def log_cb(msg):
            self.app.log(f"ipatool: {msg}")

        def worker():
            ok, msg, data = perform_login(email, pwd, passphrase, auth_code=auth_code, log_callback=log_cb)
            def update():
                self.btn_submit_login.config(state=tk.NORMAL)
                self.btn_send_2fa.config(state=tk.NORMAL)

                if ok:
                    self.lbl_login_feedback.config(text=f"تم تسجيل الدخول بنجاح! ✅ ({email})", foreground=self.app.success_color)
                    SETTINGS['keychain_passphrase'] = passphrase
                    save_settings(SETTINGS)
                    self.refresh_account_status_ui()
                    self.app.log(f"✅ تم تسجيل الدخول بنجاح: {msg}")
                    messagebox.showinfo("تم بنجاح", f"تم تسجيل الدخول بنجاح بحساب أبل:\n{email}\n\nوتم حفظ الباسورد السريع: {passphrase}")
                else:
                    self.lbl_login_feedback.config(text=f"فشل: {msg}", foreground=self.app.danger_color)
                    self.app.log(f"❌ خطأ تسجيل الدخول: {msg}")
                    messagebox.showerror(
                        "فشل تسجيل الدخول",
                        f"لم ينجح تسجيل الدخول:\n{msg}\n\n"
                        "نصيحة: يمكنك استخدام زر 'تسجيل الدخول التفاعلي عبر CMD' بالأعلى لاتباع نفس طريقة سطر الأوامر بالضبط!"
                    )

            self.app.root.after(0, update)

        self.app.run_in_thread(worker)
