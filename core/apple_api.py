import os
import re
import json
import base64
import hashlib
import subprocess
import threading
import plistlib
import urllib.request
import urllib.parse
import zipfile
import io
import time
import requests
from .config import IPATOOL_PATH, COOKIE_PATH, ACCOUNT_PATH, MAC, SETTINGS, get_keychain_passphrase, save_settings, get_download_dir
from .cache import get_cached_version, set_cached_version, save_purchases_cache, load_purchases_cache

session = requests.Session()

def validate_email_format(email):
    """يتحقق من صحة صيغة البريد الإلكتروني (Apple ID)."""
    if not email or not isinstance(email, str):
        return False, "يرجى إدخال البريد الإلكتروني."
    email = email.strip()
    if len(email) < 5 or " " in email:
        return False, "صيغة البريد الإلكتروني غير صحيحة (تأكد من عدم وجود مسافات)."
    pattern = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
    if not re.match(pattern, email):
        return False, "صيغة البريد الإلكتروني غير صحيحة! يرجى كتابة بريد صالح (مثل example@icloud.com)."
    return True, "صيغة البريد الإلكتروني صحيحة ✅"

def translate_apple_error(err_msg):
    """ترجمة وتوضيح رسائل خطأ أبل و ipatool إلى اللغة العربية الواضحة."""
    if not err_msg:
        return "حدث خطأ غير معروف أثناء الاتصال بخوادم أبل."
    low = err_msg.lower()
    if "badlogin" in low or "invalid" in low or "incorrect" in low or "-20101" in low or "password" in low and "failed to read" not in low:
        return f"البريد الإلكتروني أو كلمة المرور غير صحيحة ({err_msg})"
    if "auth code" in low or "2fa" in low or "verification" in low:
        return f"رمز التحقق (2FA) غير صحيح أو انتهت صلاحيته ({err_msg})"
    if "http 301" in low or "missing account credentials" in low:
        return f"رفض خادم أبل بيانات الدخول (تأكد من صحة البريد وكلمة المرور): {err_msg}"
    if "rate limit" in low or "too many" in low:
        return f"تم حظر المحاولات مؤقتاً بسبب كثرة الطلبات، يرجى الانتظار قليلاً ({err_msg})"
    if "locked" in low or "disabled" in low:
        return f"حساب أبل مقفل أو معطل لأسباب أمنية ({err_msg})"
    return err_msg

def reencrypt_account_keychain(old_passphrase, new_passphrase):
    """
    إعادة تشفير ملف جلسة الحساب (~/.ipatool/account) بالرمز المؤقت الجديد للحافظة
    دون الحاجة لإعادة تسجيل الدخول أو طلب كود 2FA مرة أخرى.
    """
    if not os.path.exists(ACCOUNT_PATH):
        return False, "ملف الجلسة غير موجود."
    if old_passphrase == new_passphrase:
        SETTINGS['keychain_passphrase'] = new_passphrase
        save_settings(SETTINGS)
        return True, "تم اعتماد الرمز المؤقت للحافظة بنجاح."

    try:
        from cryptography.hazmat.primitives.keywrap import aes_key_unwrap, aes_key_wrap
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        def b64url_decode(data: bytes) -> bytes:
            rem = len(data) % 4
            if rem:
                data += b'=' * (4 - rem)
            return base64.urlsafe_b64decode(data)

        def b64url_encode(data: bytes) -> bytes:
            return base64.urlsafe_b64encode(data).rstrip(b'=')

        with open(ACCOUNT_PATH, 'rb') as f:
            jwe_bytes = f.read().strip()

        parts = jwe_bytes.split(b'.')
        if len(parts) != 5:
            return False, "صيغة ملف الجلسة غير مدعومة."

        header_b64, ek_b64, iv_b64, ct_b64, tag_b64 = parts
        header = json.loads(b64url_decode(header_b64).decode('utf-8'))
        alg = header.get('alg', 'PBES2-HS256+A128KW')
        p2c = int(header.get('p2c', 8192))
        p2s = b64url_decode(header['p2s'].encode('ascii'))

        # فك التشفير بالرمز المؤقت القديم
        salt_input = alg.encode('utf-8') + b'\x00' + p2s
        old_kek = hashlib.pbkdf2_hmac('sha256', old_passphrase.encode('utf-8'), salt_input, p2c, dklen=16)
        ek = b64url_decode(ek_b64)
        cek = aes_key_unwrap(old_kek, ek)

        iv = b64url_decode(iv_b64)
        ct = b64url_decode(ct_b64)
        tag = b64url_decode(tag_b64)

        aesgcm = AESGCM(cek)
        plaintext = aesgcm.decrypt(iv, ct + tag, header_b64)

        # إعادة التشفير بالرمز المؤقت الجديد
        new_kek = hashlib.pbkdf2_hmac('sha256', new_passphrase.encode('utf-8'), salt_input, p2c, dklen=16)
        new_ek = aes_key_wrap(new_kek, cek)
        new_ek_b64 = b64url_encode(new_ek)

        new_jwe = b'.'.join([header_b64, new_ek_b64, iv_b64, ct_b64, tag_b64])
        with open(ACCOUNT_PATH, 'wb') as f:
            f.write(new_jwe)

        SETTINGS['keychain_passphrase'] = new_passphrase
        save_settings(SETTINGS)
        return True, "تم تشفير وحفظ الجلسة بالرمز المؤقت بنجاح ✅"
    except Exception as e:
        return False, f"تعذر تحديث رمز الحافظة: {str(e)}"


class InteractiveLoginSession:
    """
    يدير جلسة تسجيل دخول تفاعلية خطوة بخطوة مع ipatool:
    1. يتحقق من البريد وكلمة المرور مع أبل.
    2. يبقي عملية ipatool مفتوحة في حالة طلب رمز التحقق (enter 2FA code:) دون إغلاقها،
       حتى لو تأخر وصول الكود للهاتف.
    3. يرسل كود 2FA في نفس الجلسة المفتوحة ويتأكد من صحته.
    4. يتيح ضبط الرمز المؤقت للحافظة (Keychain Passphrase) بعد التأكد من نجاح الدخول.
    """
    def __init__(self, email, password, temp_passphrase=None, log_callback=None):
        self.email = email.strip()
        self.password = password.strip()
        self.temp_passphrase = (temp_passphrase or get_keychain_passphrase() or "2211").strip()
        self.log_callback = log_callback
        self.proc = None
        self._lines = []
        self._waiting_for_2fa = False
        self._finished = False
        self._success_info = None
        self._last_error = ""
        self._lock = threading.Lock()
        self._event_state = threading.Event()

    def _log(self, text):
        if self.log_callback and text:
            self.log_callback(text)

    def close(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None

    def verify_credentials_and_wait_2fa(self, timeout=120):
        """
        المرحلة التفاعلية للتحقق من البريد وكلمة المرور:
        تتصل بخوادم أبل وتنتظر إما:
        - نجاح الدخول مباشرة ("SUCCESS")
        - طلب كود التحقق بخطوتين ("NEEDS_2FA") مع إبقاء الجلسة حية في انتظار إدخال الكود!
        - فشل بسبب خطأ في الإيميل أو الباسورد ("ERROR")
        """
        self.close()
        self._waiting_for_2fa = False
        self._finished = False
        self._success_info = None
        self._last_error = ""
        self._event_state.clear()

        cmd = [
            IPATOOL_PATH,
            "auth",
            "login",
            "--email", self.email,
            "--password", self.password,
            "--keychain-passphrase", self.temp_passphrase,
            "--format", "json",
            "--verbose"
        ]

        try:
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            self.proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,
                startupinfo=startupinfo
            )
        except Exception as e:
            return "ERROR", f"تعذر تشغيل أداة ipatool: {str(e)}", None

        def reader():
            buf = b""
            while True:
                ch = self.proc.stdout.read(1)
                if not ch:
                    if buf:
                        self._process_line(buf.decode('utf-8', errors='ignore'))
                    with self._lock:
                        self._finished = True
                        self._event_state.set()
                    break
                buf += ch
                # Check if ipatool is prompting for 2FA code without newline
                if buf.endswith(b"enter 2FA code: ") or buf.endswith(b"enter 2FA code:"):
                    prompt_str = buf.decode('utf-8', errors='ignore').strip()
                    self._log(f"📱 أبل تطلب رمز التحقق (2FA): {prompt_str}")
                    buf = b""
                    with self._lock:
                        self._waiting_for_2fa = True
                        self._event_state.set()
                elif ch == b"\n":
                    line_str = buf.decode('utf-8', errors='ignore').strip()
                    buf = b""
                    if line_str:
                        self._process_line(line_str)

        t = threading.Thread(target=reader, daemon=True)
        t.start()

        # Wait until either 2FA prompt appears or process exits
        triggered = self._event_state.wait(timeout=timeout)
        if not triggered:
            self.close()
            return "ERROR", "انتهت مهلة الاتصال بخوادم أبل. يرجى التحقق من اتصال الإنترنت والمحاولة مجدداً.", None

        with self._lock:
            if self._waiting_for_2fa and self.proc and self.proc.poll() is None:
                return "NEEDS_2FA", "تم التأكد من صحة البريد وكلمة المرور! وتم إرسال كود التحقق (2FA) إلى جهازك.", None
            if self._success_info:
                return "SUCCESS", "تم تسجيل الدخول بنجاح دون الحاجة لرمز تحقق!", self._success_info
            err = translate_apple_error(self._last_error)
            return "ERROR", err, None

    def _process_line(self, line_str):
        # Remove possible prefix if attached to prompt
        if "enter 2FA code:" in line_str:
            parts = line_str.split("enter 2FA code:", 1)
            with self._lock:
                self._waiting_for_2fa = True
                self._event_state.set()
            line_str = parts[-1].strip()
            if not line_str:
                return

        self._log(line_str)
        try:
            data = json.loads(line_str)
            msg = data.get("message", "")
            if msg == "preparing authentication; the first login may take a few minutes":
                self._log("⏳ جاري تجهيز اتصال الأمان مع أبل (قد يستغرق لحظات)...")
            elif msg == "logging in":
                self._log("🔐 جاري فحص البريد وكلمة المرور لدى خوادم أبل...")

            if data.get("success") is True:
                with self._lock:
                    self._success_info = data
                    self._event_state.set()
            if data.get("error"):
                with self._lock:
                    self._last_error = data.get("error")
        except Exception:
            if line_str and not line_str.startswith("{"):
                with self._lock:
                    self._last_error = line_str

    def submit_2fa_code(self, auth_code, timeout=90):
        """
        إرسال كود التحقق (2FA) إلى الجلسة التفاعلية المفتوحة والتحقق من صحته مع أبل.
        إذا كانت الجلسة قد أغلقت لأي سبب، يعيد الإرسال تلقائياً مع الكود.
        """
        clean_code = str(auth_code).strip().replace(" ", "").replace("-", "")
        if not (clean_code.isdigit() and len(clean_code) == 6):
            return False, "يرجى إدخال كود التحقق المكون من 6 أرقام صحيحة.", None

        if self.proc and self.proc.poll() is None and self._waiting_for_2fa:
            try:
                with self._lock:
                    self._waiting_for_2fa = False
                    self._event_state.clear()
                    self._last_error = ""
                self.proc.stdin.write((clean_code + "\n").encode('utf-8'))
                self.proc.stdin.flush()
            except Exception:
                # Fallback to direct call if pipe broke
                return perform_login(self.email, self.password, self.temp_passphrase, auth_code=clean_code, log_callback=self.log_callback)

            # Wait for process to finish validating 2FA code
            finished = self._event_state.wait(timeout=timeout)
            if not finished:
                self.close()
                return False, "انتهت مهلة التحقق من الكود لدى خوادم أبل.", None

            # Wait briefly for process exit and final JSON line
            for _ in range(20):
                if self._success_info or self._finished:
                    break
                time.sleep(0.1)

            with self._lock:
                if self._success_info:
                    return True, "تم التحقق من صحة كود التحقق (2FA) وتسجيل الدخول بنجاح! ✅", self._success_info
                err = translate_apple_error(self._last_error)
                return False, err, None
        else:
            # Fallback if process was not kept alive
            return perform_login(self.email, self.password, self.temp_passphrase, auth_code=clean_code, log_callback=self.log_callback)

    def finalize_keychain_passphrase(self, desired_passphrase):
        """
        المرحلة الأخيرة: حفظ وتشفير الجلسة بالرمز المؤقت للحافظة الذي اختاره المستخدم،
        ثم التحقق النهائي من حالة الحساب.
        """
        desired = (desired_passphrase or "2211").strip()
        ok, msg = reencrypt_account_keychain(self.temp_passphrase, desired)
        self.temp_passphrase = desired
        info = check_auth_status(desired)
        return ok and info.get('logged_in', False), msg, info


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
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=12, startupinfo=startupinfo)
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

def perform_login(email, password, passphrase, auth_code=None, log_callback=None):
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
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, startupinfo=startupinfo)
        stdout, stderr = proc.communicate(timeout=180)

        last_error = ""
        success_info = None

        combined = stdout + "\n" + stderr
        for line in combined.strip().splitlines():
            if log_callback and line.strip():
                log_callback(line.strip())
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
            return False, translate_apple_error(last_error) if last_error else "فشل تسجيل الدخول، يرجى التأكد من البيانات أو رمز التحقق.", None
    except subprocess.TimeoutExpired:
        proc.kill()
        return False, "انتهت مهلة الاتصال بخوادم أبل (تجاوز 3 دقائق). يمكنك استخدام خيار تسجيل الدخول عبر CMD.", None
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
    out_dir = get_download_dir()
    out_file = os.path.join(out_dir, f"{clean_name}{ver_suffix}.ipa")
    passphrase = get_keychain_passphrase()
    return f'"{IPATOOL_PATH}" download --bundle-identifier {bundle_id} --external-version-id {ext_id} --keychain-passphrase {passphrase} --output "{out_file}" --purchase'

def _format_app_result(app):
    icon = (
        app.get('artworkUrl100')
        or app.get('artworkUrl512')
        or app.get('artworkUrl60')
        or ''
    )
    genres_list = app.get('genres', [])
    if not genres_list and app.get('primaryGenreName'):
        genres_list = [app['primaryGenreName']]
    return {
        'app_id': app.get('trackId'),
        'bundle_id': app.get('bundleId', ''),
        'name': app.get('trackName', ''),
        'icon_url': icon,
        'seller': app.get('sellerName', '') or app.get('artistName', ''),
        'genres': ', '.join(genres_list),
        'price': app.get('formattedPrice', 'Free'),
        'current_version': app.get('version', ''),
        'size': app.get('fileSizeBytes', '0'),
        'min_os': app.get('minimumOsVersion', ''),
        'rating': app.get('averageUserRating', None),
        'rating_count': app.get('userRatingCount', 0)
    }

def search_app(query, country='us', limit=25):
    query = str(query).strip()
    if not query:
        return []

    results = []
    seen_ids = set()

    # 1. Lookup by bundle ID if dots exist (bundle ID pattern)
    if '.' in query:
        url = f'https://itunes.apple.com/lookup?bundleId={urllib.parse.quote(query)}&country={country}'
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as res:
                data = json.loads(res.read().decode('utf-8'))
                for app in data.get('results', []):
                    track_id = app.get('trackId')
                    if track_id and track_id not in seen_ids:
                        seen_ids.add(track_id)
                        results.append(_format_app_result(app))
        except Exception:
            pass

    # 2. Lookup by ID if numeric
    if query.isdigit():
        url_id = f'https://itunes.apple.com/lookup?id={query}&country={country}'
        try:
            req = urllib.request.Request(url_id, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as res:
                data = json.loads(res.read().decode('utf-8'))
                for app in data.get('results', []):
                    track_id = app.get('trackId')
                    if track_id and track_id not in seen_ids:
                        seen_ids.add(track_id)
                        results.append(_format_app_result(app))
        except Exception:
            pass

    # 3. Search by term
    url2 = f'https://itunes.apple.com/search?term={urllib.parse.quote(query)}&entity=software&limit={limit}&country={country}'
    try:
        req = urllib.request.Request(url2, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as res:
            data = json.loads(res.read().decode('utf-8'))
            for app in data.get('results', []):
                track_id = app.get('trackId')
                if track_id and track_id not in seen_ids:
                    seen_ids.add(track_id)
                    results.append(_format_app_result(app))
    except Exception:
        pass

    return results

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

def _enrich_purchased_apps(apps):
    if not apps:
        return []

    enriched = []
    ids = [str(a.get('id')) for a in apps if a.get('id')]

    id_map = {}
    batch_size = 50
    for i in range(0, len(ids), batch_size):
        batch = ids[i:i + batch_size]
        url = f"https://itunes.apple.com/lookup?id={','.join(batch)}&country=us"
        try:
            resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                for r in data.get('results', []):
                    track_id = r.get('trackId')
                    if track_id:
                        id_map[track_id] = r
                        id_map[str(track_id)] = r
                    bid = r.get('bundleId')
                    if bid:
                        id_map[bid] = r
        except Exception:
            pass

    for a in apps:
        app_id = a.get('id')
        bundle_id = a.get('bundleID', '')
        lookup_info = id_map.get(app_id) or id_map.get(str(app_id)) or id_map.get(bundle_id) or {}

        icon_url = (
            lookup_info.get('artworkUrl100')
            or lookup_info.get('artworkUrl512')
            or lookup_info.get('artworkUrl60')
            or ''
        )

        genres = lookup_info.get('genres', [])
        if not genres and lookup_info.get('primaryGenreName'):
            genres = [lookup_info['primaryGenreName']]

        price_val = a.get('price', 0)
        formatted_price = lookup_info.get('formattedPrice', 'مجاني' if price_val == 0 else f"${price_val}")

        enriched.append({
            'app_id': app_id,
            'bundle_id': bundle_id or lookup_info.get('bundleId', ''),
            'name': a.get('name', '') or lookup_info.get('trackName', ''),
            'icon_url': icon_url,
            'current_version': a.get('version', '') or lookup_info.get('version', ''),
            'seller': lookup_info.get('sellerName', '') or lookup_info.get('artistName', ''),
            'genres': ', '.join(genres),
            'price': formatted_price,
            'size': lookup_info.get('fileSizeBytes', '0'),
            'purchase_date': a.get('purchaseDate', ''),
            'platforms': a.get('platforms', []),
            'min_os': lookup_info.get('minimumOsVersion', ''),
            'rating': lookup_info.get('averageUserRating', None)
        })

    return enriched

def get_account_purchases(passphrase=None, max_results=100, page=1, retry_count=2):
    """جلب التطبيقات المشتراة والمملوكة لحساب أبل"""
    if not passphrase:
        passphrase = get_keychain_passphrase()

    cmd = [
        IPATOOL_PATH,
        'list-purchases',
        '--keychain-passphrase', passphrase,
        '--format', 'json',
        '--non-interactive',
        '--max-results', str(max_results),
        '--page', str(page)
    ]

    last_error = ""
    for attempt in range(retry_count + 1):
        try:
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                startupinfo=startupinfo,
                timeout=30
            )

            stdout = proc.stdout.strip()
            if not stdout:
                last_error = proc.stderr.strip() or "لم يتم استلام استجابة من خوادم أبل"
                time.sleep(1)
                continue

            data = None
            for line in stdout.splitlines():
                line = line.strip()
                if line.startswith('{') and line.endswith('}'):
                    try:
                        data = json.loads(line)
                        break
                    except Exception:
                        pass

            if not data:
                last_error = stdout
                time.sleep(1)
                continue

            if data.get('level') == 'error' or (not data.get('apps') and data.get('error')):
                err = data.get('error', 'خطأ غير معروف')
                last_error = translate_apple_error(err)
                if ('timeout' in err.lower() or 'tls' in err.lower()) and attempt < retry_count:
                    time.sleep(1.5)
                    continue
                return False, last_error, []

            apps = data.get('apps', [])
            enriched = _enrich_purchased_apps(apps)
            save_purchases_cache(enriched)
            return True, "تم جلب التطبيقات بنجاح", enriched

        except subprocess.TimeoutExpired:
            last_error = "انتهت مهلة الاتصال بخوادم أبل (Timeout)"
            time.sleep(1)
            continue
        except Exception as e:
            last_error = str(e)
            time.sleep(1)

    cached = load_purchases_cache()
    if cached:
        return True, "تم تحميل التطبيقات من الذاكرة المؤقتة (تعذر الاتصال بالخادم)", cached

    return False, last_error or "تعذر جلب التطبيقات من حساب أبل", []

def purchase_license(bundle_id, passphrase=None):
    """شراء ترخيص مجاني للتطبيق وإضافته إلى حساب أبل مباشرة عبر ipatool"""
    if not passphrase:
        passphrase = get_keychain_passphrase()

    cmd = [
        IPATOOL_PATH,
        'purchase',
        '--bundle-identifier', bundle_id,
        '--keychain-passphrase', passphrase,
        '--format', 'json',
        '--non-interactive'
    ]

    try:
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            startupinfo=startupinfo,
            timeout=25
        )

        stdout = proc.stdout.strip()
        data = None
        for line in stdout.splitlines():
            line = line.strip()
            if line.startswith('{') and line.endswith('}'):
                try:
                    data = json.loads(line)
                    break
                except Exception:
                    pass

        if not data:
            return False, proc.stderr.strip() or stdout or "فشل الحصول على ترخيص التطبيق"

        if data.get('level') == 'error' or not data.get('success', False):
            err = data.get('error', 'فشل الحصول على ترخيص التطبيق')
            return False, translate_apple_error(err)

        return True, "تم الحصول على ترخيص التطبيق بنجاح وأصبح متاحاً للتحميل في حسابك! 🎉"
    except Exception as e:
        return False, str(e)
