import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import threading
import concurrent.futures
import json
import plistlib
import urllib.request
import urllib.parse
import zipfile
import io
import os
import subprocess
import sys
import time
import requests

# --- Configuration & Settings ---
SETTINGS_FILE = r'C:\DRIVERS\settings.json'

def load_settings():
    defaults = {
        'keychain_passphrase': '2211',
        'download_dir': r'C:\DRIVERS'
    }
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                defaults.update(data)
        except Exception:
            pass
    return defaults

def save_settings(settings):
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

SETTINGS = load_settings()

# --- Constants & Paths ---
MAC = '94659C755502'
COOKIE_PATH = os.path.expanduser(r'~\\.ipatool\cookies')
ACCOUNT_PATH = os.path.expanduser(r'~\\.ipatool\account')
IPATOOL_DIR = os.path.expanduser(r'~\\.ipatool')
IPATOOL_PATH = r'C:\DRIVERS\ipatool.exe'
CACHE_FILE = r'C:\DRIVERS\versions_cache.json'
SAVED_QUEUE_FILE = r'C:\DRIVERS\saved_downloads.json'

def get_keychain_passphrase():
    return SETTINGS.get('keychain_passphrase', '2211')

def get_download_dir():
    return SETTINGS.get('download_dir', r'C:\DRIVERS')

# --- Thread-Safe Cache ---
cache_lock = threading.Lock()
VERSIONS_CACHE = {}

def load_cache():
    global VERSIONS_CACHE
    with cache_lock:
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    VERSIONS_CACHE = json.load(f)
            except Exception:
                VERSIONS_CACHE = {}
        else:
            VERSIONS_CACHE = {}

def save_cache():
    with cache_lock:
        try:
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(VERSIONS_CACHE, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

def get_cached_version(app_id, ext_id):
    key = f"{app_id}_{ext_id}"
    with cache_lock:
        return VERSIONS_CACHE.get(key)

def set_cached_version(app_id, ext_id, info):
    key = f"{app_id}_{ext_id}"
    with cache_lock:
        VERSIONS_CACHE[key] = info
    save_cache()

load_cache()

# --- Persistent Saved Queue Management ---
saved_queue_lock = threading.Lock()

def load_saved_queue():
    with saved_queue_lock:
        if os.path.exists(SAVED_QUEUE_FILE):
            try:
                with open(SAVED_QUEUE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return []
        return []

def save_saved_queue(items):
    with saved_queue_lock:
        try:
            with open(SAVED_QUEUE_FILE, 'w', encoding='utf-8') as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

def add_to_saved_queue(app_name, bundle_id, app_id, ext_id, version="?", min_os="?"):
    items = load_saved_queue()
    item_id = f"{bundle_id}_{ext_id}"
    for it in items:
        if it.get('id') == item_id:
            updated = False
            if version != "?" and it.get('version') == "?":
                it['version'] = version
                updated = True
            if min_os != "?" and it.get('min_os') == "?":
                it['min_os'] = min_os
                updated = True
            if updated:
                save_saved_queue(items)
            return False, "هذا الإصدار موجود مسبقاً في قائمة التنزيلات المحفوظة."

    clean_name = "".join(c for c in app_name if c.isalnum() or c in (' ', '_', '-')).strip().replace(" ", "_")
    if not clean_name:
        clean_name = bundle_id
    ver_suffix = f"_{version}" if version and version != "?" else f"_{ext_id}"
    file_name = f"{clean_name}{ver_suffix}.ipa"
    out_path = os.path.join(get_download_dir(), file_name)

    new_item = {
        'id': item_id,
        'app_name': app_name,
        'bundle_id': bundle_id,
        'app_id': str(app_id),
        'ext_id': str(ext_id),
        'version': version if version else "?",
        'min_os': min_os if min_os else "?",
        'status': 'في الانتظار ⏳',
        'downloaded': False,
        'file_path': out_path,
        'date_added': time.strftime('%Y-%m-%d %H:%M')
    }
    items.insert(0, new_item)
    save_saved_queue(items)
    return True, f"تم حفظ {app_name} (إصدار {version}) في قائمة التنزيلات لاحقاً."

def remove_from_saved_queue(item_ids):
    items = load_saved_queue()
    id_set = set(item_ids)
    new_items = [it for it in items if it.get('id') not in id_set]
    save_saved_queue(new_items)
    return len(items) - len(new_items)

def update_saved_queue_item(item_id, **kwargs):
    items = load_saved_queue()
    for it in items:
        if it.get('id') == item_id:
            for k, v in kwargs.items():
                it[k] = v
            break
    save_saved_queue(items)

# Shared requests session
session = requests.Session()

# --- Authentication Helpers via ipatool ---

def check_auth_status(passphrase=None):
    if not passphrase:
        passphrase = get_keychain_passphrase()
    cmd = [
        IPATOOL_PATH,
        "auth",
        "info",
        "--keychain-passphrase", passphrase,
        "--format", "json",
        "--non-interactive"
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        for line in res.stdout.strip().splitlines():
            try:
                data = json.loads(line)
                if data.get('success'):
                    return {
                        'logged_in': True,
                        'name': data.get('name', '').strip(),
                        'email': data.get('email', '').strip(),
                        'time': data.get('time', '')
                    }
            except Exception:
                pass
    except Exception:
        pass
    return {'logged_in': False, 'name': '', 'email': '', 'time': ''}

def perform_login(email, password, passphrase, auth_code=None):
    cmd = [
        IPATOOL_PATH,
        "auth",
        "login",
        "--email", email.strip(),
        "--password", password.strip(),
        "--keychain-passphrase", passphrase.strip(),
        "--format", "json",
        "--non-interactive"
    ]
    if auth_code and str(auth_code).strip():
        cmd.extend(["--auth-code", str(auth_code).strip()])

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = proc.communicate(timeout=65)

        last_error = ""
        success_info = None

        combined = stdout + "\n" + stderr
        for line in combined.strip().splitlines():
            try:
                data = json.loads(line)
                if data.get('success') is True:
                    success_info = data
                if data.get('error'):
                    last_error = data.get('error')
            except Exception:
                if line.strip() and not line.startswith('{'):
                    last_error = line.strip()

        if success_info:
            return True, "تم تسجيل الدخول بنجاح! ✅", success_info
        else:
            return False, last_error if last_error else "فشل تسجيل الدخول، يرجى التأكد من البيانات أو رمز التحقق.", None
    except subprocess.TimeoutExpired:
        return False, "انتهت مهلة الاتصال بخوادم أبل (Timeout). حاول مرة أخرى.", None
    except Exception as e:
        return False, f"خطأ غير متوقع: {str(e)}", None

def perform_revoke(passphrase=None):
    if not passphrase:
        passphrase = get_keychain_passphrase()
    cmd = [
        IPATOOL_PATH,
        "auth",
        "revoke",
        "--keychain-passphrase", passphrase,
        "--format", "json",
        "--non-interactive"
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return True, "تم إلغاء تسجيل الدخول بنجاح."
    except Exception as e:
        return False, str(e)

# --- Backend Helper Functions ---

def get_cookies():
    try:
        if not os.path.exists(COOKIE_PATH):
            return ""
        with open(COOKIE_PATH, 'r', encoding='utf-8') as f:
            cookies = json.load(f)
        cookie_parts = [f"{c['Name']}={c['Value']}" for c in cookies if c.get('Value') and c.get('Name')]
        return '; '.join(cookie_parts)
    except Exception:
        return ""

def get_apple_headers():
    dsid = '20912319274'
    return {
        'Content-Type': 'application/x-apple-plist',
        'iCloud-DSID': dsid,
        'X-Dsid': dsid,
        'User-Agent': 'Configurator/2.17 (Macintosh; OS X 15.2; 24C5089c) AppleWebKit/0620.1.16.11.6',
        'Cookie': get_cookies()
    }

def generate_download_cmd(bundle_id, ext_id, app_name="", version=""):
    clean_name = "".join(c for c in app_name if c.isalnum() or c in (' ', '_', '-')).strip().replace(" ", "_")
    if not clean_name:
        clean_name = bundle_id
    ver_suffix = f"_{version}" if version and version != "?" else f"_{ext_id}"
    out_file = f"{clean_name}{ver_suffix}.ipa"
    passphrase = get_keychain_passphrase()
    return f'"{IPATOOL_PATH}" download --bundle-identifier {bundle_id} --external-version-id {ext_id} --keychain-passphrase {passphrase} --output "{out_file}" --purchase'

def search_app(query, country='us'):
    url = f'https://itunes.apple.com/lookup?bundleId={query}&country={country}'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as res:
            data = json.loads(res.read().decode('utf-8'))
            if data.get('results'):
                app = data['results'][0]
                return {
                    'app_id': app['trackId'],
                    'bundle_id': app['bundleId'],
                    'name': app.get('trackName', query),
                    'icon_url': app.get('artworkUrl100', ''),
                    'seller': app.get('sellerName', ''),
                    'genres': ', '.join(app.get('genres', [])),
                    'price': app.get('formattedPrice', 'Free'),
                    'current_version': app.get('version', ''),
                    'size': app.get('fileSizeBytes', '0')
                }
    except Exception:
        pass

    url2 = f'https://itunes.apple.com/search?term={urllib.parse.quote(query)}&entity=software&limit=10&country={country}'
    try:
        req = urllib.request.Request(url2, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as res:
            data = json.loads(res.read().decode('utf-8'))
            results = []
            for app in data.get('results', []):
                results.append({
                    'app_id': app['trackId'],
                    'bundle_id': app['bundleId'],
                    'name': app.get('trackName', ''),
                    'icon_url': app.get('artworkUrl100', ''),
                    'seller': app.get('sellerName', ''),
                    'genres': ', '.join(app.get('genres', [])),
                    'price': app.get('formattedPrice', 'Free'),
                    'current_version': app.get('version', ''),
                    'size': app.get('fileSizeBytes', '0')
                })
            return results if len(results) != 1 else results[0]
    except Exception:
        pass
    return None

def get_latest_ext_id(app_id, country='us'):
    url = f'https://uclient-api.itunes.apple.com/WebObjects/MZStorePlatform.woa/wa/lookup?version=2&id={app_id}&p=mdm-lockup&caller=MDM&platform=iphone&cc={country}&l=en'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'ipatool'})
        with urllib.request.urlopen(req, timeout=10) as res:
            plat_data = json.loads(res.read().decode('utf-8'))
            results = plat_data.get('results', {})
            if str(app_id) in results:
                offers = results[str(app_id)].get('offers', [])
                if offers:
                    v = offers[0].get('version', {})
                    return str(v.get('externalId')), v.get('display', '')
    except Exception:
        pass
    return None, ''

def get_all_version_ids(app_id, latest_ext_id):
    payload = {
        'creditDisplay': '',
        'guid': MAC,
        'salableAdamId': int(app_id),
        'serialNumber': '0',
        'appExtVrsId': str(latest_ext_id)
    }
    try:
        plist_bytes = plistlib.dumps(payload, fmt=plistlib.FMT_XML)
        url = f'https://downloaddispatch.itunes.apple.com/up/updateProduct?guid={MAC}'
        headers = get_apple_headers()
        resp = session.post(url, data=plist_bytes, headers=headers, timeout=20)
        res = plistlib.loads(resp.content)
        items = res.get('songList', [])
        if items:
            return items[0].get('metadata', {}).get('softwareVersionExternalIdentifiers', [])
    except Exception:
        pass
    return []

# --- Buffered Remote Zip Reader ---

class BufferedRemoteZipReader(io.RawIOBase):
    def __init__(self, url, sess):
        self.url = url
        self.sess = sess
        resp = self.sess.get(url, headers={'Range': 'bytes=0-0'}, timeout=25)
        cr = resp.headers.get('Content-Range', '')
        self.size = int(cr.split('/')[-1]) if cr else 0
        self.pos = 0
        self.buffer = b''
        self.buffer_start = 0

    def seek(self, offset, whence=io.SEEK_SET):
        if whence == io.SEEK_SET:
            self.pos = offset
        elif whence == io.SEEK_CUR:
            self.pos += offset
        elif whence == io.SEEK_END:
            self.pos = self.size + offset
        return self.pos

    def tell(self):
        return self.pos

    def read(self, size=-1):
        if size == -1 or self.pos + size > self.size:
            size = self.size - self.pos
        if size <= 0:
            return b""

        if self.buffer_start <= self.pos < self.buffer_start + len(self.buffer):
            offset_in_buf = self.pos - self.buffer_start
            available = len(self.buffer) - offset_in_buf
            if available >= size:
                self.pos += size
                return self.buffer[offset_in_buf:offset_in_buf + size]

        fetch_size = max(size, 131072)
        if self.pos + fetch_size > self.size:
            fetch_size = self.size - self.pos

        end = self.pos + fetch_size - 1
        resp = self.sess.get(self.url, headers={'Range': f'bytes={self.pos}-{end}'}, timeout=35)
        data = resp.content
        self.buffer = data
        self.buffer_start = self.pos

        result = data[:size]
        self.pos += len(result)
        return result

def get_version_info(app_id, external_version_id, retries=2):
    cached = get_cached_version(app_id, external_version_id)
    if cached:
        return cached

    for attempt in range(retries):
        try:
            payload = {
                'creditDisplay': '',
                'guid': MAC,
                'salableAdamId': int(app_id),
                'serialNumber': '0',
                'appExtVrsId': str(external_version_id)
            }
            plist_bytes = plistlib.dumps(payload, fmt=plistlib.FMT_XML)
            url = f'https://downloaddispatch.itunes.apple.com/up/updateProduct?guid={MAC}'
            headers = get_apple_headers()
            post_resp = session.post(url, data=plist_bytes, headers=headers, timeout=25)
            res = plistlib.loads(post_resp.content)
            items = res.get('songList', [])
            if not items:
                continue
            dl_url = items[0].get('URL')
            if not dl_url:
                continue

            rz = BufferedRemoteZipReader(dl_url, session)
            zf = zipfile.ZipFile(rz)
            for name in zf.namelist():
                if name.startswith('Payload/') and name.endswith('.app/Info.plist'):
                    with zf.open(name) as pf:
                        plist_data = plistlib.loads(pf.read())
                        info = {
                            'displayVersion': plist_data.get('CFBundleShortVersionString', ''),
                            'minOS': plist_data.get('MinimumOSVersion', '?'),
                            'bundleVersion': plist_data.get('CFBundleVersion', ''),
                            'externalId': str(external_version_id)
                        }
                        set_cached_version(app_id, external_version_id, info)
                        return info
        except Exception:
            time.sleep(1)
            continue
    return None

def download_ipa(bundle_id, ext_id, output_path, progress_callback=None):
    passphrase = get_keychain_passphrase()
    cmd = [
        IPATOOL_PATH,
        'download',
        '--bundle-identifier', bundle_id,
        '--external-version-id', str(ext_id),
        '--keychain-passphrase', passphrase,
        '--output', output_path,
        '--purchase'
    ]
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in process.stdout:
            if progress_callback:
                progress_callback(line.strip())
        process.wait()
        return process.returncode == 0
    except Exception as e:
        if progress_callback:
            progress_callback(f"Error executing ipatool: {str(e)}")
        return False

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

# --- GUI Application ---

class IPAManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("مدير تطبيقات IPA (الشامل: كاش + فحص متوازي + قائمة التحميل + تسجيل الدخول)")
        self.root.geometry("1060x820")

        # Color Scheme
        self.bg_color = "#1e1e2e"
        self.fg_color = "#cdd6f4"
        self.accent_color = "#89b4fa"
        self.alt_bg = "#313244"
        self.success_color = "#a6e3a1"
        self.danger_color = "#f38ba8"

        self.root.configure(bg=self.bg_color)

        # State
        self.current_app = None
        self.current_latest_ext_id = None
        self.current_versions = []
        self.scan_cancel_requested = False
        self.scan_in_progress = False

        # Queue State
        self.queue_cancel_requested = False
        self.queue_in_progress = False

        self.setup_styles()
        self.build_ui()
        self.refresh_saved_queue_ui()
        self.refresh_account_status_ui()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure(".", background=self.bg_color, foreground=self.fg_color, font=("Segoe UI", 10))
        style.configure("TFrame", background=self.bg_color)
        style.configure("Alt.TFrame", background=self.alt_bg)

        style.configure("TLabel", background=self.bg_color, foreground=self.fg_color)
        style.configure("Header.TLabel", font=("Segoe UI", 11, "bold"))
        style.configure("Title.TLabel", font=("Segoe UI", 13, "bold"), foreground=self.accent_color)
        style.configure("Sub.TLabel", font=("Segoe UI", 9), foreground="#a6adc8")

        style.configure("TButton", background=self.alt_bg, foreground=self.fg_color, borderwidth=1, focuscolor=self.accent_color)
        style.map("TButton", background=[("active", self.accent_color)], foreground=[("active", self.bg_color)])
        style.configure("Accent.TButton", background=self.accent_color, foreground=self.bg_color, font=("Segoe UI", 10, "bold"))
        style.configure("Success.TButton", background=self.success_color, foreground="#11111b", font=("Segoe UI", 10, "bold"))
        style.configure("Danger.TButton", background=self.danger_color, foreground=self.bg_color, font=("Segoe UI", 10, "bold"))

        style.configure("TEntry", fieldbackground=self.alt_bg, foreground=self.fg_color, insertcolor=self.fg_color, borderwidth=1)

        style.configure("TNotebook", background=self.bg_color, borderwidth=0)
        style.configure("TNotebook.Tab", background=self.alt_bg, foreground=self.fg_color, padding=[14, 6])
        style.map("TNotebook.Tab", background=[("selected", self.accent_color)], foreground=[("selected", self.bg_color)])

        style.configure("Treeview", background=self.alt_bg, foreground=self.fg_color, fieldbackground=self.alt_bg, borderwidth=0, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background=self.bg_color, foreground=self.accent_color, font=("Segoe UI", 10, "bold"))
        style.map("Treeview", background=[("selected", self.accent_color)], foreground=[("selected", self.bg_color)])

        style.configure("Horizontal.TProgressbar", background=self.accent_color, troughcolor=self.alt_bg)

    def build_ui(self):
        # --- Top: Search Bar ---
        top_frame = ttk.Frame(self.root)
        top_frame.pack(fill=tk.X, padx=20, pady=(15, 8))

        self.btn_search = ttk.Button(top_frame, text="بحث 🔍", command=self.on_search, style="Accent.TButton")
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

        self.lbl_app_name = ttk.Label(self.info_card, text="", style="Title.TLabel", anchor='e')
        self.lbl_app_name.pack(fill=tk.X, padx=15, pady=(8, 2))

        self.lbl_app_details = ttk.Label(self.info_card, text="يرجى كتابة اسم التطبيق والضغط على بحث (يدعم النسخ واللصق الكامل)", anchor='e', justify='right')
        self.lbl_app_details.pack(fill=tk.X, padx=15, pady=(0, 4))

        # Quick action buttons for loaded app
        self.info_btn_frame = ttk.Frame(self.info_card, style="Alt.TFrame")
        self.info_btn_frame.pack(fill=tk.X, padx=15, pady=(0, 8))

        self.btn_save_latest = ttk.Button(self.info_btn_frame, text="حفظ أحدث إصدار للتحميل لاحقاً 💾", command=self.on_save_latest_to_queue)
        self.btn_save_latest.pack(side=tk.RIGHT, padx=5)

        self.btn_copy_latest_cmd = ttk.Button(self.info_btn_frame, text="نسخ أمر التحميل (CMD) 📋", command=self.on_copy_latest_cmd)
        self.btn_copy_latest_cmd.pack(side=tk.RIGHT, padx=5)

        self.info_btn_frame.pack_forget()

        # Tabs Notebook
        self.notebook = ttk.Notebook(self.middle_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.build_tab_quick()
        self.build_tab_versions()
        self.build_tab_compatible()
        self.build_tab_saved_queue()
        self.build_tab_account()

        # --- Bottom: Console ---
        bottom_frame = ttk.Frame(self.root)
        bottom_frame.pack(fill=tk.X, padx=20, pady=(0, 12))

        console_header = ttk.Frame(bottom_frame)
        console_header.pack(fill=tk.X)

        ttk.Label(console_header, text="سجل العمليات:", style="Header.TLabel").pack(side=tk.RIGHT)
        ttk.Button(console_header, text="مسح السجل", command=lambda: self.console.delete(1.0, tk.END)).pack(side=tk.LEFT)

        self.console = scrolledtext.ScrolledText(bottom_frame, height=5, bg=self.alt_bg, fg=self.fg_color,
                                                 insertbackground=self.fg_color, font=("Consolas", 9))
        self.console.pack(fill=tk.X, pady=(4, 0))
        self.console.bind("<Key>", lambda e: "break")

    def build_tab_quick(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="  تحميل سريع  ")

        content = ttk.Frame(tab)
        content.pack(expand=True, fill=tk.BOTH, padx=30, pady=25)

        self.lbl_quick_status = ttk.Label(content, text="جاهز للتحميل", font=("Segoe UI", 11), anchor='center')
        self.lbl_quick_status.pack(fill=tk.X, pady=(15, 10))

        btn_box = ttk.Frame(content)
        btn_box.pack(pady=15)

        self.btn_quick_download = ttk.Button(btn_box, text="تحميل أحدث إصدار ⬇️", command=self.on_quick_download, style="Accent.TButton")
        self.btn_quick_download.pack(side=tk.LEFT, padx=10, ipadx=15, ipady=5)

    def build_tab_versions(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="  استعراض وفحص الإصدارات  ")

        top_ctrl = ttk.Frame(tab)
        top_ctrl.pack(fill=tk.X, padx=10, pady=(8, 4))

        self.btn_load_versions = ttk.Button(top_ctrl, text="تحميل قائمة الإصدارات 🔄", command=self.on_load_versions, style="Accent.TButton")
        self.btn_load_versions.pack(side=tk.RIGHT, padx=5)

        self.lbl_versions_count = ttk.Label(top_ctrl, text="", style="Header.TLabel")
        self.lbl_versions_count.pack(side=tk.RIGHT, padx=15)

        # Batch Scan Controls Frame
        scan_ctrl = ttk.Frame(tab, style="Alt.TFrame")
        scan_ctrl.pack(fill=tk.X, padx=10, pady=5)

        f_top_n = ttk.Frame(scan_ctrl, style="Alt.TFrame")
        f_top_n.pack(side=tk.RIGHT, padx=8, pady=5)

        self.btn_scan_top_n = ttk.Button(f_top_n, text="فحص أحدث الإصدارات ⚡", command=self.on_scan_top_n)
        self.btn_scan_top_n.pack(side=tk.RIGHT, padx=4)

        self.entry_top_n = ttk.Entry(f_top_n, width=4, justify='center')
        self.entry_top_n.insert(0, "15")
        self.entry_top_n.pack(side=tk.RIGHT, padx=2)
        setup_entry_clipboard(self.root, self.entry_top_n)

        ttk.Label(f_top_n, text=":عدد", background=self.alt_bg).pack(side=tk.RIGHT, padx=2)

        f_range = ttk.Frame(scan_ctrl, style="Alt.TFrame")
        f_range.pack(side=tk.RIGHT, padx=12, pady=5)

        self.btn_scan_range = ttk.Button(f_range, text="فحص النطاق 🎯", command=self.on_scan_range)
        self.btn_scan_range.pack(side=tk.RIGHT, padx=4)

        self.entry_range_to = ttk.Entry(f_range, width=5, justify='center')
        self.entry_range_to.insert(0, "")
        self.entry_range_to.pack(side=tk.RIGHT, padx=2)
        setup_entry_clipboard(self.root, self.entry_range_to)

        ttk.Label(f_range, text="إلى #:", background=self.alt_bg).pack(side=tk.RIGHT, padx=2)

        self.entry_range_from = ttk.Entry(f_range, width=5, justify='center')
        self.entry_range_from.insert(0, "")
        self.entry_range_from.pack(side=tk.RIGHT, padx=2)
        setup_entry_clipboard(self.root, self.entry_range_from)

        ttk.Label(f_range, text="من #:", background=self.alt_bg).pack(side=tk.RIGHT, padx=2)

        self.btn_cancel_scan = ttk.Button(scan_ctrl, text="إلغاء ⏹️", command=self.on_cancel_scan, style="Danger.TButton", state=tk.DISABLED)
        self.btn_cancel_scan.pack(side=tk.LEFT, padx=10, pady=5)

        self.scan_prog_bar = ttk.Progressbar(scan_ctrl, orient="horizontal", mode="determinate", length=120, style="Horizontal.TProgressbar")
        self.scan_prog_bar.pack(side=tk.LEFT, padx=5, pady=5)

        self.lbl_scan_status = ttk.Label(scan_ctrl, text="", background=self.alt_bg)
        self.lbl_scan_status.pack(side=tk.LEFT, padx=5)

        # Treeview for Versions
        tree_frame = ttk.Frame(tab)
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

        self.ctx_menu = tk.Menu(self.root, tearoff=0, bg=self.alt_bg, fg=self.fg_color)
        self.ctx_menu.add_command(label="فحص التوافق لهذا الإصدار 🔍", command=self.on_check_compatibility)
        self.ctx_menu.add_command(label="تحميل هذا الإصدار الآن ⬇️", command=self.on_download_selected)
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command(label="حفظ هذا الإصدار للتحميل لاحقاً 💾", command=self.on_save_selected_to_queue)
        self.ctx_menu.add_command(label="نسخ أمر التحميل (CMD) 📋", command=self.on_copy_selected_cmd)

        self.tree.bind("<Button-3>", self.show_context_menu)

    def build_tab_compatible(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="  البحث الذكي عن إصدار متوافق  ")

        content = ttk.Frame(tab)
        content.pack(expand=True, fill=tk.BOTH, padx=30, pady=25)

        input_frame = ttk.Frame(content)
        input_frame.pack(pady=15)

        self.entry_target_os = ttk.Entry(input_frame, justify='center', width=8, font=("Segoe UI", 12))
        self.entry_target_os.insert(0, "15.8")
        self.entry_target_os.pack(side=tk.LEFT, padx=10)
        setup_entry_clipboard(self.root, self.entry_target_os)

        ttk.Label(input_frame, text=":إصدار iOS المستهدف لجهازك", font=("Segoe UI", 12, "bold")).pack(side=tk.LEFT)

        self.btn_auto_search = ttk.Button(content, text="بحث ذكي تلقائي 🔍", command=self.on_auto_search, style="Accent.TButton")
        self.btn_auto_search.pack(pady=10, ipadx=15, ipady=4)

        self.lbl_search_result = ttk.Label(content, text="", font=("Segoe UI", 11), justify='center')
        self.lbl_search_result.pack(pady=15)

        self.compat_btn_frame = ttk.Frame(content)
        self.compat_btn_frame.pack(pady=10)

        self.btn_download_compatible = ttk.Button(self.compat_btn_frame, text="تحميل هذا الإصدار المتوافق ⬇️", command=self.on_download_compatible, style="Accent.TButton")
        self.btn_download_compatible.pack(side=tk.LEFT, padx=8, ipadx=12, ipady=4)

        self.btn_save_compatible = ttk.Button(self.compat_btn_frame, text="حفظ للتحميل لاحقاً 💾", command=self.on_save_compatible_to_queue)
        self.btn_save_compatible.pack(side=tk.LEFT, padx=8, ipadx=12, ipady=4)

        self.btn_copy_compatible_cmd = ttk.Button(self.compat_btn_frame, text="نسخ أمر التحميل (CMD) 📋", command=self.on_copy_compatible_cmd)
        self.btn_copy_compatible_cmd.pack(side=tk.LEFT, padx=8, ipadx=12, ipady=4)

        self.compat_btn_frame.pack_forget()

    def build_tab_saved_queue(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="  التحميلات المحفوظة 💾  ")

        top_bar = ttk.Frame(tab, style="Alt.TFrame")
        top_bar.pack(fill=tk.X, padx=10, pady=(8, 6))

        self.btn_queue_download_sel = ttk.Button(top_bar, text="تحميل المحدد ⬇️", command=self.on_queue_download_selected, style="Success.TButton")
        self.btn_queue_download_sel.pack(side=tk.RIGHT, padx=5, pady=6)

        self.btn_queue_download_all = ttk.Button(top_bar, text="تحميل الكل ⬇️⬇️", command=self.on_queue_download_all, style="Accent.TButton")
        self.btn_queue_download_all.pack(side=tk.RIGHT, padx=5, pady=6)

        self.btn_queue_stop = ttk.Button(top_bar, text="إيقاف التحميل ⏹️", command=self.on_queue_stop, style="Danger.TButton", state=tk.DISABLED)
        self.btn_queue_stop.pack(side=tk.RIGHT, padx=5, pady=6)

        self.btn_queue_copy_cmd = ttk.Button(top_bar, text="نسخ أمر التحميل 📋", command=self.on_queue_copy_cmd)
        self.btn_queue_copy_cmd.pack(side=tk.RIGHT, padx=5, pady=6)

        self.btn_queue_delete = ttk.Button(top_bar, text="حذف من القائمة 🗑️", command=self.on_queue_delete_selected)
        self.btn_queue_delete.pack(side=tk.RIGHT, padx=5, pady=6)

        self.btn_queue_refresh = ttk.Button(top_bar, text="تحديث 🔄", command=self.refresh_saved_queue_ui)
        self.btn_queue_refresh.pack(side=tk.LEFT, padx=8, pady=6)

        self.lbl_queue_stats = ttk.Label(top_bar, text="", background=self.alt_bg, font=("Segoe UI", 10, "bold"))
        self.lbl_queue_stats.pack(side=tk.LEFT, padx=10, pady=6)

        tree_frame = ttk.Frame(tab)
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

        self.queue_ctx_menu = tk.Menu(self.root, tearoff=0, bg=self.alt_bg, fg=self.fg_color)
        self.queue_ctx_menu.add_command(label="تحميل المحدد الآن ⬇️", command=self.on_queue_download_selected)
        self.queue_ctx_menu.add_command(label="نسخ أمر التحميل (CMD) 📋", command=self.on_queue_copy_cmd)
        self.queue_ctx_menu.add_separator()
        self.queue_ctx_menu.add_command(label="حذف من القائمة 🗑️", command=self.on_queue_delete_selected)
        self.queue_ctx_menu.add_command(label="مسح المكتمل فقط 🧹", command=self.on_queue_clear_completed)

        self.queue_tree.bind("<Button-3>", self.show_queue_context_menu)

    def build_tab_account(self):
        """Tab 5: Account & Login Management (Apple ID, Passwords, 2FA)"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="  الحساب وتسجيل الدخول 👤  ")

        canvas = tk.Canvas(tab, bg=self.bg_color, highlightthickness=0)
        vscroll = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        scroll_content = ttk.Frame(canvas)

        scroll_content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_content, anchor="nw", width=1010)
        canvas.configure(yscrollcommand=vscroll.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=10)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y, pady=10)

        # Card 1: Current Account Status & Storage Info
        card_status = ttk.Frame(scroll_content, style="Alt.TFrame")
        card_status.pack(fill=tk.X, padx=15, pady=(5, 12))

        ttk.Label(card_status, text="حالة الحساب الحالي ومكان تخزين البيانات 🔐", style="Title.TLabel", anchor='e').pack(fill=tk.X, padx=15, pady=(12, 6))

        self.lbl_acc_status_badge = ttk.Label(card_status, text="جاري فحص حالة الحساب...", font=("Segoe UI", 11, "bold"), anchor='e')
        self.lbl_acc_status_badge.pack(fill=tk.X, padx=15, pady=2)

        self.lbl_acc_name_email = ttk.Label(card_status, text="", font=("Segoe UI", 10), anchor='e')
        self.lbl_acc_name_email.pack(fill=tk.X, padx=15, pady=2)

        desc_storage = (
            f"📁 مكان تخزين بيانات تسجيل الدخول على جهازك:\n"
            f"   • المسار: {IPATOOL_DIR}\n"
            f"   • ملف account: مشفر ومحمي بتشفير AES-256 (مفتاحه السري هو الباسورد المؤقت مثل {get_keychain_passphrase()})\n"
            f"   • ملف cookies: يحتوي على كوكيز الجلسة للتواصل مع متجر أبل"
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

        # Card 2: Login Form (Email, Password, 2FA, Passphrase)
        card_login = ttk.Frame(scroll_content, style="Alt.TFrame")
        card_login.pack(fill=tk.X, padx=15, pady=(0, 15))

        ttk.Label(card_login, text="تسجيل الدخول بحساب أبل (Apple ID) 🔑", style="Title.TLabel", anchor='e').pack(fill=tk.X, padx=15, pady=(12, 6))

        info_steps = (
            "💡 طريقة تسجيل الدخول مع التحقق بخطوتين (2FA):\n"
            "1. اكتب البريد الإلكتروني وكلمة المرور الخاصة بحساب أبل والباسورد السريع للحافظة.\n"
            "2. اضغط على 'طلب رمز التحقق 📱' لتصلك رسالة أبل على الايفون بموافقة وتسليم كود 6 أرقام.\n"
            "3. اكتب الرمز المكون من 6 أرقام ثم اضغط على 'تأكيد وتسجيل الدخول 🔐'."
        )
        ttk.Label(card_login, text=info_steps, style="Sub.TLabel", justify='right', anchor='e').pack(fill=tk.X, padx=15, pady=(0, 10))

        grid_frame = ttk.Frame(card_login, style="Alt.TFrame")
        grid_frame.pack(fill=tk.X, padx=20, pady=5)

        # Row 1: Apple ID Email
        ttk.Label(grid_frame, text="بريد أبل (Apple ID Email):", style="Header.TLabel", background=self.alt_bg).grid(row=0, column=2, sticky='e', padx=10, pady=8)
        self.entry_login_email = ttk.Entry(grid_frame, width=38, font=("Segoe UI", 10), justify='left')
        self.entry_login_email.grid(row=0, column=1, sticky='w', padx=5, pady=8)
        self.entry_login_email.insert(0, "bkr7728282@gmail.com")
        setup_entry_clipboard(self.root, self.entry_login_email)

        # Row 2: Apple ID Password
        ttk.Label(grid_frame, text="كلمة مرور حساب أبل:", style="Header.TLabel", background=self.alt_bg).grid(row=1, column=2, sticky='e', padx=10, pady=8)
        f_pass = ttk.Frame(grid_frame, style="Alt.TFrame")
        f_pass.grid(row=1, column=1, sticky='w', padx=5, pady=8)

        self.entry_login_pass = ttk.Entry(f_pass, width=30, font=("Segoe UI", 10), show="*", justify='left')
        self.entry_login_pass.pack(side=tk.LEFT)
        setup_entry_clipboard(self.root, self.entry_login_pass)

        self.pass_visible = False
        def toggle_pass_vis():
            self.pass_visible = not self.pass_visible
            self.entry_login_pass.config(show="" if self.pass_visible else "*")
            btn_show_pass.config(text="🙈" if self.pass_visible else "👁️")

        btn_show_pass = ttk.Button(f_pass, text="👁️", width=3, command=toggle_pass_vis)
        btn_show_pass.pack(side=tk.LEFT, padx=4)

        # Row 3: Keychain Passphrase (e.g. 2211)
        ttk.Label(grid_frame, text="الباسورد السريع للحافظة (Keychain):", style="Header.TLabel", background=self.alt_bg).grid(row=2, column=2, sticky='e', padx=10, pady=8)
        self.entry_login_keychain = ttk.Entry(grid_frame, width=15, font=("Segoe UI", 10), justify='center')
        self.entry_login_keychain.grid(row=2, column=1, sticky='w', padx=5, pady=8)
        self.entry_login_keychain.insert(0, get_keychain_passphrase())
        setup_entry_clipboard(self.root, self.entry_login_keychain)

        ttk.Label(grid_frame, text="(كلمة مرور محلية لتشفير الاعتمادات مثل 2211)", style="Sub.TLabel", background=self.alt_bg).grid(row=2, column=0, sticky='w', padx=5, pady=8)

        # Row 4: 2FA Code
        ttk.Label(grid_frame, text="رمز التحقق بخطوتين (2FA Code):", style="Header.TLabel", background=self.alt_bg).grid(row=3, column=2, sticky='e', padx=10, pady=8)
        self.entry_login_2fa = ttk.Entry(grid_frame, width=15, font=("Segoe UI", 12, "bold"), justify='center')
        self.entry_login_2fa.grid(row=3, column=1, sticky='w', padx=5, pady=8)
        setup_entry_clipboard(self.root, self.entry_login_2fa)

        ttk.Label(grid_frame, text="(كود الـ 6 أرقام الواصل لهاتفك الايفون)", style="Sub.TLabel", background=self.alt_bg).grid(row=3, column=0, sticky='w', padx=5, pady=8)

        # Row 5: Action buttons
        btn_action_frame = ttk.Frame(card_login, style="Alt.TFrame")
        btn_action_frame.pack(pady=(12, 10))

        self.btn_send_2fa = ttk.Button(btn_action_frame, text="1️⃣ طلب رمز التحقق (إرسال الرمز للايفون) 📱", command=self.on_request_2fa_code, style="Accent.TButton")
        self.btn_send_2fa.pack(side=tk.LEFT, padx=10, ipadx=12, ipady=5)

        self.btn_submit_login = ttk.Button(btn_action_frame, text="2️⃣ تأكيد وتسجيل الدخول 🔐", command=self.on_submit_login, style="Success.TButton")
        self.btn_submit_login.pack(side=tk.LEFT, padx=10, ipadx=15, ipady=5)

        # Row 6: Status feedback label
        self.lbl_login_feedback = ttk.Label(card_login, text="", font=("Segoe UI", 10, "bold"), anchor='center', background=self.alt_bg)
        self.lbl_login_feedback.pack(fill=tk.X, padx=20, pady=(0, 15))

    # --- Account Tab Actions ---

    def refresh_account_status_ui(self):
        self.lbl_acc_status_badge.config(text="جاري التحقق من بيانات الحساب...")
        self.run_in_thread(self._check_account_worker)

    def _check_account_worker(self):
        passphrase = get_keychain_passphrase()
        info = check_auth_status(passphrase)

        def update():
            if info['logged_in']:
                self.lbl_acc_status_badge.config(text="الحالة: مسجل الدخول بنجاح ✅", foreground=self.success_color)
                self.lbl_acc_name_email.config(text=f"الاسم: {info['name']}   |   الحساب: {info['email']}   |   الباسورد السريع: {passphrase}")
                self.log(f"الحساب متصل: {info['name']} ({info['email']})")
            else:
                self.lbl_acc_status_badge.config(text="الحالة: غير مسجل الدخول أو بحاجة لتجديد الاعتماد ❌", foreground=self.danger_color)
                self.lbl_acc_name_email.config(text="يرجى تسجيل الدخول بحساب أبل من النموذج بالأسفل")
                self.log("الحساب غير متصل حالياً.")

        self.root.after(0, update)

    def on_open_storage_folder(self):
        try:
            if not os.path.exists(IPATOOL_DIR):
                os.makedirs(IPATOOL_DIR, exist_ok=True)
            os.startfile(IPATOOL_DIR)
            self.log(f"تم فتح مجلد تخزين الحساب: {IPATOOL_DIR}")
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذر فتح المجلد: {str(e)}")

    def on_logout(self):
        if not messagebox.askyesno("تسجيل الخروج", "هل أنت متأكد من تسجيل الخروج وإلغاء الاعتماد من متجر أبل؟"):
            return
        passphrase = get_keychain_passphrase()
        self.log("جاري تسجيل الخروج...")
        self.run_in_thread(self._logout_worker, passphrase)

    def _logout_worker(self, passphrase):
        ok, msg = perform_revoke(passphrase)
        self.log(msg)
        self.root.after(0, lambda: messagebox.showinfo("تسجيل الخروج", msg))
        self.root.after(0, self.refresh_account_status_ui)

    def on_request_2fa_code(self):
        email = self.entry_login_email.get().strip()
        pwd = self.entry_login_pass.get().strip()
        passphrase = self.entry_login_keychain.get().strip()

        if not email or not pwd:
            messagebox.showerror("بيانات ناقصة", "يرجى كتابة البريد الإلكتروني وكلمة المرور لحساب أبل أولاً.")
            return

        if not passphrase:
            passphrase = "2211"
            self.entry_login_keychain.insert(0, "2211")

        self.lbl_login_feedback.config(text="جاري إرسال طلب تسجيل الدخول لأبل لإرسال كود التحقق لهاتفك...", foreground=self.accent_color)
        self.btn_send_2fa.config(state=tk.DISABLED)
        self.btn_submit_login.config(state=tk.DISABLED)
        self.log(f"طلب رمز 2FA للحساب: {email}...")

        def worker():
            ok, msg, data = perform_login(email, pwd, passphrase, auth_code=None)
            def update():
                self.btn_send_2fa.config(state=tk.NORMAL)
                self.btn_submit_login.config(state=tk.NORMAL)

                if ok:
                    # Logged in directly (e.g. if 2FA wasn't needed or session was recognized)
                    self.lbl_login_feedback.config(text="تم تسجيل الدخول بنجاح! ✅", foreground=self.success_color)
                    SETTINGS['keychain_passphrase'] = passphrase
                    save_settings(SETTINGS)
                    self.refresh_account_status_ui()
                    messagebox.showinfo("نجاح", "تم تسجيل الدخول بنجاح!")
                else:
                    # Usually Apple sends the 2FA code to devices and returns error prompting for code
                    self.lbl_login_feedback.config(
                        text="📱 تم إرسال الرمز لجهاز الايفون! اكتب الكود المكون من 6 أرقام واضغط 'تأكيد وتسجيل الدخول'",
                        foreground="#f9e2af"
                    )
                    self.log(f"استجابة أبل: {msg}")
                    self.entry_login_2fa.focus_set()
                    messagebox.showinfo("رمز التحقق", "إذا كان الحساب يدعم التحقق بخطوتين، فقد تم إرسال رمز 6 أرقام إلى جهاز الايفون الخاص بك.\n\nيرجى كتابة الرمز في حقل 'رمز التحقق' ثم الضغط على الزر 2.")

            self.root.after(0, update)

        self.run_in_thread(worker)

    def on_submit_login(self):
        email = self.entry_login_email.get().strip()
        pwd = self.entry_login_pass.get().strip()
        passphrase = self.entry_login_keychain.get().strip()
        auth_code = self.entry_login_2fa.get().strip()

        if not email or not pwd:
            messagebox.showerror("بيانات ناقصة", "يرجى كتابة البريد الإلكتروني وكلمة المرور.")
            return

        if not passphrase:
            passphrase = "2211"

        self.lbl_login_feedback.config(text="جاري توثيق تسجيل الدخول مع خوادم أبل...", foreground=self.accent_color)
        self.btn_submit_login.config(state=tk.DISABLED)
        self.btn_send_2fa.config(state=tk.DISABLED)
        self.log(f"جاري إرسال الاعتماد مع كود {auth_code if auth_code else 'فارغ'}...")

        def worker():
            ok, msg, data = perform_login(email, pwd, passphrase, auth_code=auth_code)
            def update():
                self.btn_submit_login.config(state=tk.NORMAL)
                self.btn_send_2fa.config(state=tk.NORMAL)

                if ok:
                    self.lbl_login_feedback.config(text=f"تم تسجيل الدخول بنجاح! ✅ ({email})", foreground=self.success_color)
                    SETTINGS['keychain_passphrase'] = passphrase
                    save_settings(SETTINGS)
                    self.refresh_account_status_ui()
                    self.log(f"✅ تم تسجيل الدخول بنجاح: {msg}")
                    messagebox.showinfo("تم بنجاح", f"تم تسجيل الدخول بنجاح بحساب أبل:\n{email}\n\nوتم حفظ الباسورد السريع: {passphrase}")
                else:
                    self.lbl_login_feedback.config(text=f"فشل: {msg}", foreground=self.danger_color)
                    self.log(f"❌ خطأ تسجيل الدخول: {msg}")
                    messagebox.showerror("خطأ في تسجيل الدخول", f"لم ينجح تسجيل الدخول:\n{msg}")

            self.root.after(0, update)

        self.run_in_thread(worker)

    # --- Clipboard Helper ---

    def copy_text_to_clipboard(self, text, message="تم نسخ النص إلى الحافظة!"):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()
        self.log(f"📋 {message}")
        messagebox.showinfo("تم النسخ", f"{message}\n\nالأمر المنسوخ:\n{text}")

    # --- Utilities ---

    def log(self, message):
        def update():
            self.console.insert(tk.END, f"> {message}\n")
            self.console.see(tk.END)
        self.root.after(0, update)

    def show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.ctx_menu.post(event.x_root, event.y_root)

    def show_queue_context_menu(self, event):
        item = self.queue_tree.identify_row(event.y)
        if item:
            if item not in self.queue_tree.selection():
                self.queue_tree.selection_set(item)
            self.queue_ctx_menu.post(event.x_root, event.y_root)

    def run_in_thread(self, func, *args):
        threading.Thread(target=func, args=args, daemon=True).start()

    # --- Actions: Search & App Info ---

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
                self.root.after(0, lambda: messagebox.showinfo("بحث", "لم يتم العثور على التطبيق."))
                return

            if isinstance(results, list):
                self.log(f"تم العثور على {len(results)} نتيجة.")
                self._search_results = results
                self.root.after(0, self._show_results_dialog)
                return
            else:
                app = results

            self._select_app(app)

        except Exception as e:
            self.log(f"خطأ أثناء البحث: {str(e)}")
        finally:
            self.root.after(0, lambda: self.btn_search.config(state=tk.NORMAL))

    def _show_results_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("اختر التطبيق")
        dialog.geometry("520x360")
        dialog.configure(bg=self.bg_color)
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="تم العثور على عدة نتائج، اختر التطبيق:", style="Header.TLabel").pack(padx=15, pady=12, anchor='e')

        listbox = tk.Listbox(dialog, bg=self.alt_bg, fg=self.fg_color,
                             font=("Segoe UI", 10), selectbackground=self.accent_color,
                             selectforeground=self.bg_color, borderwidth=0, highlightthickness=0)
        listbox.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 10))

        for r in self._search_results:
            listbox.insert(tk.END, f"{r['name']} — {r['bundle_id']} ({r['seller']})")

        if self._search_results:
            listbox.select_set(0)

        def on_select():
            sel = listbox.curselection()
            if sel:
                app = self._search_results[sel[0]]
                dialog.destroy()
                self.run_in_thread(self._select_app, app)

        ttk.Button(dialog, text="اختيار هذا التطبيق ✅", command=on_select, style="Accent.TButton").pack(pady=(0, 15))

    def _select_app(self, app):
        self.current_app = app
        self.log(f"تم اختيار التطبيق: {app['name']}")

        ext_id, display_ver = get_latest_ext_id(app['app_id'])
        self.current_latest_ext_id = ext_id

        if display_ver and not app['current_version']:
            app['current_version'] = display_ver

        self.root.after(0, self._update_app_info)
        self.root.after(0, lambda: self.btn_search.config(state=tk.NORMAL))

    def _update_app_info(self):
        app = self.current_app
        size_fmt = format_size(app['size'])
        self.lbl_app_name.config(text=app['name'])

        details = (
            f"Bundle ID: {app['bundle_id']}   |   App ID: {app['app_id']}\n"
            f"المطور: {app['seller']}   |   أحدث إصدار: {app['current_version']} (معرف: {self.current_latest_ext_id})\n"
            f"الحجم: {size_fmt}   |   السعر: {app['price']}"
        )
        self.lbl_app_details.config(text=details)
        self.info_btn_frame.pack(fill=tk.X, padx=15, pady=(0, 8))

        # Reset tabs
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.current_versions = []
        self.lbl_versions_count.config(text="")
        self.lbl_quick_status.config(text="جاهز للتحميل")
        self.compat_btn_frame.pack_forget()
        self.lbl_search_result.config(text="")
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

    # --- Actions: Tab 1 Quick Download ---

    def on_quick_download(self):
        if not self.current_app or not self.current_latest_ext_id:
            messagebox.showwarning("تنبيه", "الرجاء البحث عن تطبيق أولاً")
            return

        self.btn_quick_download.config(state=tk.DISABLED)
        ext_id = self.current_latest_ext_id
        bundle_id = self.current_app['bundle_id']
        app_name = "".join(c for c in self.current_app['name'] if c.isalnum() or c in (' ', '_', '-')).strip().replace(" ", "_")
        out_path = os.path.join(get_download_dir(), f"{app_name}_{ext_id}.ipa")

        self.log(f"بدء التحميل السريع للتطبيق {bundle_id} بإصدار {ext_id}...")
        self.run_in_thread(self._download_worker, bundle_id, ext_id, out_path, self.lbl_quick_status, self.btn_quick_download)

    def _download_worker(self, bundle_id, ext_id, out_path, status_label, enable_btn):
        def cb(msg):
            self.log(msg)
            self.root.after(0, lambda: status_label.config(text=msg[:60] + "..." if len(msg) > 60 else msg))

        success = download_ipa(bundle_id, ext_id, out_path, cb)

        if success:
            msg = f"تم التحميل بنجاح! ✅\nالمسار: {out_path}"
        else:
            msg = "فشل التحميل. راجع السجل للتفاصيل. ❌"

        self.root.after(0, lambda: status_label.config(text=msg))
        self.root.after(0, lambda: enable_btn.config(state=tk.NORMAL))

    # --- Actions: Tab 2 Versions & Context Menu ---

    def on_load_versions(self):
        if not self.current_app or not self.current_latest_ext_id:
            messagebox.showwarning("تنبيه", "الرجاء البحث عن تطبيق أولاً")
            return

        self.btn_load_versions.config(state=tk.DISABLED)
        self.log("جاري جلب قائمة الإصدارات من خوادم أبل...")
        self.run_in_thread(self._load_versions_worker)

    def _load_versions_worker(self):
        app_id = self.current_app['app_id']
        latest_ext_id = self.current_latest_ext_id

        versions = get_all_version_ids(app_id, latest_ext_id)

        if not versions:
            self.log("لم يتم العثور على إصدارات أو حدث خطأ في الاتصال.")
            self.root.after(0, lambda: self.btn_load_versions.config(state=tk.NORMAL))
            return

        self.current_versions = versions
        self.log(f"تم جلب {len(versions)} إصدار بنجاح.")

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

        self.root.after(0, update_ui)

    def on_check_compatibility(self):
        selected = self.tree.selection()
        if not selected:
            return

        item = selected[0]
        ext_id = self.tree.item(item, "values")[3]
        app_id = self.current_app['app_id']

        self.log(f"جاري فحص توافق الإصدار {ext_id}...")
        self.tree.set(item, "status", "جاري الفحص...")
        self.run_in_thread(self._check_single_worker, app_id, ext_id, item)

    def _check_single_worker(self, app_id, ext_id, tree_item):
        info = get_version_info(app_id, ext_id)
        if info:
            self.log(f"نتيجة {ext_id}: إصدار {info['displayVersion']} (iOS {info['minOS']})")
            def update():
                self.tree.set(tree_item, "min_os", info['minOS'])
                self.tree.set(tree_item, "version", info['displayVersion'])
                self.tree.set(tree_item, "status", "تم الفحص ✅")
            self.root.after(0, update)
        else:
            self.log(f"فشل فحص الإصدار {ext_id}")
            self.root.after(0, lambda: self.tree.set(tree_item, "status", "فشل الفحص ❌"))

    def on_download_selected(self):
        selected = self.tree.selection()
        if not selected:
            return

        item = selected[0]
        ext_id = self.tree.item(item, "values")[3]
        ver_str = self.tree.item(item, "values")[2]
        bundle_id = self.current_app['bundle_id']

        clean_name = "".join(c for c in self.current_app['name'] if c.isalnum() or c in (' ', '_', '-')).strip().replace(" ", "_")
        ver_suffix = f"_{ver_str}" if ver_str and ver_str != "?" else f"_{ext_id}"
        out_path = os.path.join(get_download_dir(), f"{clean_name}{ver_suffix}.ipa")

        self.log(f"بدء تحميل الإصدار {ext_id}...")
        self.tree.set(item, "status", "جاري التحميل...")

        def cb(msg):
            self.log(msg)
            self.root.after(0, lambda: self.tree.set(item, "status", "تحميل..."))

        def worker():
            success = download_ipa(bundle_id, ext_id, out_path, cb)
            msg = "اكتمل التحميل ✅" if success else "فشل التحميل ❌"
            self.root.after(0, lambda: self.tree.set(item, "status", msg))

        self.run_in_thread(worker)

    def on_save_selected_to_queue(self):
        selected = self.tree.selection()
        if not selected:
            return

        item = selected[0]
        vals = self.tree.item(item, "values")
        ext_id = vals[3]
        ver_str = vals[2]
        min_os = vals[1]

        app = self.current_app
        ok, msg = add_to_saved_queue(
            app_name=app['name'],
            bundle_id=app['bundle_id'],
            app_id=app['app_id'],
            ext_id=ext_id,
            version=ver_str,
            min_os=min_os
        )
        self.log(msg)
        self.refresh_saved_queue_ui()
        messagebox.showinfo("قائمة التنزيل المحفوظة", msg)

    def on_copy_selected_cmd(self):
        selected = self.tree.selection()
        if not selected:
            return

        item = selected[0]
        vals = self.tree.item(item, "values")
        ext_id = vals[3]
        ver_str = vals[2]

        app = self.current_app
        cmd = generate_download_cmd(app['bundle_id'], ext_id, app['name'], ver_str)
        self.copy_text_to_clipboard(cmd, f"تم نسخ أمر تحميل الإصدار {ext_id}")

    # --- Batch Parallel Scanning ---

    def on_scan_top_n(self):
        if not self.current_versions:
            messagebox.showwarning("تنبيه", "يرجى تحميل قائمة الإصدارات أولاً")
            return

        try:
            n = int(self.entry_top_n.get().strip())
            if n <= 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("خطأ", "يرجى إدخال عدد صحيح موجب (مثلاً 15 أو 20)")
            return

        top_vids = list(reversed(self.current_versions))[:n]
        self.start_batch_scan(top_vids)

    def on_scan_range(self):
        if not self.current_versions:
            messagebox.showwarning("تنبيه", "يرجى تحميل قائمة الإصدارات أولاً")
            return

        try:
            f = int(self.entry_range_from.get().strip())
            t = int(self.entry_range_to.get().strip())
        except ValueError:
            messagebox.showerror("خطأ", "يرجى إدخال أرقام صحيحة لنطاق الفهرس")
            return

        total = len(self.current_versions)
        start_idx = min(f, t)
        end_idx = max(f, t)

        start_idx = max(1, start_idx)
        end_idx = min(total, end_idx)

        selected_vids = []
        for idx in range(end_idx, start_idx - 1, -1):
            selected_vids.append(self.current_versions[idx - 1])

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

        self.log(f"بدء الفحص المتوازي لـ {len(vids_to_scan)} إصدار...")
        self.run_in_thread(self._batch_scan_worker, vids_to_scan)

    def on_cancel_scan(self):
        self.scan_cancel_requested = True
        self.lbl_scan_status.config(text="جاري الإلغاء...")
        self.log("تم طلب إلغاء الفحص...")

    def _batch_scan_worker(self, vids_to_scan):
        app_id = self.current_app['app_id']
        total = len(vids_to_scan)
        completed = 0

        def mark_pending():
            for vid in vids_to_scan:
                vid_str = str(vid)
                if self.tree.exists(vid_str):
                    curr_status = self.tree.item(vid_str, "values")[0]
                    if "محفوظ" not in curr_status:
                        self.tree.set(vid_str, "status", "في الانتظار...")
        self.root.after(0, mark_pending)

        def scan_single(vid):
            if self.scan_cancel_requested:
                return vid, None
            vid_str = str(vid)
            self.root.after(0, lambda: self.tree.set(vid_str, "status", "جاري الفحص...") if self.tree.exists(vid_str) else None)
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

                    self.root.after(0, update_row)
                except Exception as e:
                    self.log(f"خطأ أثناء فحص إصدار: {str(e)}")

        def finish():
            self.scan_in_progress = False
            self.btn_scan_top_n.config(state=tk.NORMAL)
            self.btn_scan_range.config(state=tk.NORMAL)
            self.btn_cancel_scan.config(state=tk.DISABLED)
            msg = "تم الانتهاء من الفحص بنجاح!" if not self.scan_cancel_requested else "تم إلغاء الفحص."
            self.lbl_scan_status.config(text=msg)
            self.log(msg)

        self.root.after(0, finish)

    # --- Actions: Tab 3 Smart Compatible Search ---

    def on_auto_search(self):
        if not self.current_app or not self.current_latest_ext_id:
            messagebox.showwarning("تنبيه", "الرجاء البحث عن تطبيق أولاً")
            return

        target_os = self.entry_target_os.get().strip()
        if not target_os:
            return

        self.btn_auto_search.config(state=tk.DISABLED)
        self.compat_btn_frame.pack_forget()
        self.lbl_search_result.config(text="جاري البحث الذكي...")
        self.log(f"بدء البحث الذكي عن إصدار متوافق مع iOS {target_os}...")

        self.run_in_thread(self._auto_search_worker, target_os)

    def _auto_search_worker(self, target_os):
        app_id = self.current_app['app_id']

        versions = self.current_versions
        if not versions:
            self.log("جاري جلب قائمة الإصدارات أولاً...")
            versions = get_all_version_ids(app_id, self.current_latest_ext_id)
            if versions:
                self.current_versions = versions

        if not versions:
            self.root.after(0, lambda: self.lbl_search_result.config(text="فشل جلب قائمة الإصدارات من خادم أبل."))
            self.root.after(0, lambda: self.btn_auto_search.config(state=tk.NORMAL))
            return

        # Check latest version first
        latest_ext = str(versions[-1])
        self.log(f"فحص أحدث إصدار متاح أولاً (ID: {latest_ext})...")
        latest_info = get_version_info(app_id, latest_ext)

        if latest_info and is_os_le(latest_info['minOS'], target_os):
            self.log(f"أحدث إصدار متوافق بالفعل مع جهازك! (iOS {latest_info['minOS']})")
            self._show_compatible_result(latest_info)
            return

        self.log(f"أحدث إصدار يتطلب نظاماً أحدث. جاري البحث بين {len(versions)} إصدار تاريخي...")

        low = 0
        high = len(versions) - 1
        best_match = None
        step_count = 0

        while low <= high:
            step_count += 1
            mid = (low + high) // 2
            ext_id = str(versions[mid])
            self.log(f"خطوة {step_count}: فحص الإصدار {mid + 1}/{len(versions)} (ID: {ext_id})...")

            info = get_version_info(app_id, ext_id)
            if not info:
                self.log(f"تنبيه: تعذر قراءة الإصدار {ext_id}، جاري اختبار إصدار مجاور...")
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

            self.log(f"نتيجة الفحص: إصدار {info['displayVersion']} يتطلب iOS {info['minOS']}")

            if is_os_le(info['minOS'], target_os):
                best_match = info
                low = mid + 1
            else:
                high = mid - 1

        if best_match:
            self._show_compatible_result(best_match)
        else:
            self.log("لم يتم العثور على إصدار متوافق.")
            self.root.after(0, lambda: self.lbl_search_result.config(text="عذراً، لم يتم العثور على أي إصدار متوافق مع نظامك."))
            self.root.after(0, lambda: self.btn_auto_search.config(state=tk.NORMAL))

    def _show_compatible_result(self, match):
        res_text = (
            f"🎉 تم العثور على أنسب وأحدث إصدار متوافق بنجاح!\n\n"
            f"اسم الإصدار: {match['displayVersion']}   |   أقل iOS مطلوب: {match['minOS']}\n"
            f"معرف الإصدار (External ID): {match['externalId']}"
        )
        self.log(f"تم العثور على الإصدار المتوافق: {match['displayVersion']} (ID: {match['externalId']})")
        self.compatible_match = match

        self.root.after(0, lambda: self.lbl_search_result.config(text=res_text))
        self.root.after(0, lambda: self.compat_btn_frame.pack(pady=10))
        self.root.after(0, lambda: self.btn_auto_search.config(state=tk.NORMAL))

    def on_download_compatible(self):
        if not hasattr(self, 'compatible_match'):
            return

        match = self.compatible_match
        ext_id = match['externalId']
        ver_str = match['displayVersion']
        bundle_id = self.current_app['bundle_id']
        app_name = "".join(c for c in self.current_app['name'] if c.isalnum() or c in (' ', '_', '-')).strip().replace(" ", "_")
        out_path = os.path.join(get_download_dir(), f"{app_name}_{ver_str}.ipa")

        self.btn_download_compatible.config(state=tk.DISABLED)
        self.log(f"بدء تحميل الإصدار المتوافق {ver_str}...")

        def cb(msg):
            self.log(msg)

        def worker():
            success = download_ipa(bundle_id, ext_id, out_path, cb)
            msg = "اكتمل تحميل الإصدار المتوافق بنجاح! ✅" if success else "فشل تحميل الإصدار المتوافق. ❌"
            self.log(msg)
            self.root.after(0, lambda: self.lbl_search_result.config(text=msg + f"\nالمسار: {out_path}"))
            self.root.after(0, lambda: self.btn_download_compatible.config(state=tk.NORMAL))

        self.run_in_thread(worker)

    def on_save_compatible_to_queue(self):
        if not hasattr(self, 'compatible_match'):
            return
        match = self.compatible_match
        app = self.current_app
        ok, msg = add_to_saved_queue(
            app_name=app['name'],
            bundle_id=app['bundle_id'],
            app_id=app['app_id'],
            ext_id=match['externalId'],
            version=match['displayVersion'],
            min_os=match['minOS']
        )
        self.log(msg)
        self.refresh_saved_queue_ui()
        messagebox.showinfo("قائمة التنزيل المحفوظة", msg)

    def on_copy_compatible_cmd(self):
        if not hasattr(self, 'compatible_match'):
            return
        match = self.compatible_match
        app = self.current_app
        cmd = generate_download_cmd(app['bundle_id'], match['externalId'], app['name'], match['displayVersion'])
        self.copy_text_to_clipboard(cmd, f"تم نسخ أمر تحميل الإصدار المتوافق {match['displayVersion']}")

    # --- Actions: Tab 4 Saved Downloads Queue ---

    def refresh_saved_queue_ui(self):
        for item in self.queue_tree.get_children():
            self.queue_tree.delete(item)

        items = load_saved_queue()
        completed = sum(1 for it in items if it.get('downloaded', False))
        total = len(items)
        pending = total - completed

        self.lbl_queue_stats.config(text=f"إجمالي المحفوظ: {total}  |  تم التحميل: {completed} ✅  |  في الانتظار: {pending} ⏳")

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
        self.copy_text_to_clipboard(full_cmd_text, f"تم نسخ أوامر التحميل لـ {len(cmds)} تطبيق بنجاح!")

    def on_queue_delete_selected(self):
        selected = self.queue_tree.selection()
        if not selected:
            messagebox.showinfo("تنبيه", "يرجى تحديد العناصر المراد حذفها من القائمة.")
            return

        if not messagebox.askyesno("تأكيد الحذف", f"هل أنت متأكد من حذف {len(selected)} عنصر من قائمة التحميلات المحفوظة؟"):
            return

        removed = remove_from_saved_queue(selected)
        self.log(f"تم حذف {removed} عنصر من قائمة التنزيل المحفوظة.")
        self.refresh_saved_queue_ui()

    def on_queue_clear_completed(self):
        items = load_saved_queue()
        completed_ids = [it.get('id') for it in items if it.get('downloaded', False)]
        if not completed_ids:
            messagebox.showinfo("تنبيه", "لا توجد عناصر مكتملة لحذفها.")
            return

        remove_from_saved_queue(completed_ids)
        self.log(f"تم مسح {len(completed_ids)} عنصر مكتمل من القائمة.")
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
        self.log("تم طلب إيقاف تحميل القائمة...")

    def start_queue_download_worker(self, items_to_download):
        if self.queue_in_progress:
            messagebox.showinfo("تنبيه", "هناك عملية تحميل قيد التشغيل بالفعل.")
            return

        self.queue_in_progress = True
        self.queue_cancel_requested = False

        self.btn_queue_download_sel.config(state=tk.DISABLED)
        self.btn_queue_download_all.config(state=tk.DISABLED)
        self.btn_queue_stop.config(state=tk.NORMAL)

        self.log(f"بدء تحميل قائمة التنزيل لـ {len(items_to_download)} تطبيق...")
        self.run_in_thread(self._queue_worker, items_to_download)

    def _queue_worker(self, items_to_download):
        for index, item in enumerate(items_to_download):
            if self.queue_cancel_requested:
                self.log("تم إيقاف التحميل بناءً على طلبك.")
                break

            item_id = item['id']
            app_name = item['app_name']
            ext_id = item['ext_id']
            bundle_id = item['bundle_id']
            ver_str = item.get('version', '')
            out_path = item.get('file_path')

            if not out_path:
                clean_name = "".join(c for c in app_name if c.isalnum() or c in (' ', '_', '-')).strip().replace(" ", "_")
                ver_suffix = f"_{ver_str}" if ver_str and ver_str != "?" else f"_{ext_id}"
                out_path = os.path.join(get_download_dir(), f"{clean_name}{ver_suffix}.ipa")

            self.log(f"\n--- [{index + 1}/{len(items_to_download)}] بدء تحميل {app_name} (إصدار {ver_str}) ---")

            def mark_downloading(i_id=item_id):
                if self.queue_tree.exists(i_id):
                    self.queue_tree.set(i_id, "status", "جاري التحميل... ⏳")
            self.root.after(0, mark_downloading)

            update_saved_queue_item(item_id, status="جاري التحميل... ⏳")

            def cb(msg):
                self.log(msg)

            success = download_ipa(bundle_id, ext_id, out_path, cb)

            if success:
                new_status = "تم التحميل بنجاح ✅"
                update_saved_queue_item(item_id, status=new_status, downloaded=True, file_path=out_path)
                self.log(f"✅ اكتمل تحميل {app_name} بنجاح! المسار: {out_path}")
            else:
                new_status = "فشل التحميل ❌"
                update_saved_queue_item(item_id, status=new_status, downloaded=False)
                self.log(f"❌ فشل تحميل {app_name}.")

            def mark_result(i_id=item_id, st=new_status):
                if self.queue_tree.exists(i_id):
                    self.queue_tree.set(i_id, "status", st)
                self.refresh_saved_queue_ui()
            self.root.after(0, mark_result)

        def finish():
            self.queue_in_progress = False
            self.btn_queue_download_sel.config(state=tk.NORMAL)
            self.btn_queue_download_all.config(state=tk.NORMAL)
            self.btn_queue_stop.config(state=tk.DISABLED)
            msg = "اكتملت معالجة قائمة التحميل!" if not self.queue_cancel_requested else "توقف التحميل."
            self.log(msg)
            self.refresh_saved_queue_ui()

        self.root.after(0, finish)

if __name__ == "__main__":
    root = tk.Tk()
    app = IPAManagerApp(root)
    root.mainloop()
