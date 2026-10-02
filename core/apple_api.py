import os
import json
import subprocess
import plistlib
import urllib.request
import urllib.parse
import zipfile
import io
import time
import requests
from .config import IPATOOL_PATH, COOKIE_PATH, MAC, get_keychain_passphrase
from .cache import get_cached_version, set_cached_version

session = requests.Session()

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
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
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
            return False, last_error if last_error else "فشل تسجيل الدخول، يرجى التأكد من البيانات أو رمز التحقق.", None
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
