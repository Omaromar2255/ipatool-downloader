import os
import json
import shutil

# --- Base Directory of the Application ---
# Since config.py is in 'core/', BASE_DIR is the parent directory (project root)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- Configuration & Settings Files ---
SETTINGS_FILE = os.path.join(BASE_DIR, 'settings.json')
CACHE_FILE = os.path.join(BASE_DIR, 'versions_cache.json')
SAVED_QUEUE_FILE = os.path.join(BASE_DIR, 'saved_downloads.json')

def find_ipatool_executable():
    # 1. Search in BASE_DIR for known executable names
    for name in ['ipatool.exe', 'ipatool', 'ipatoo.exe', 'ipatoo']:
        cand = os.path.join(BASE_DIR, name)
        if os.path.isfile(cand):
            return cand
    # 2. Search in system PATH
    for name in ['ipatool', 'ipatoo']:
        w = shutil.which(name)
        if w:
            return w
    # 3. Default fallback to ipatool.exe in BASE_DIR
    return os.path.join(BASE_DIR, 'ipatool.exe')

IPATOOL_PATH = find_ipatool_executable()

# --- User-level Apple Tool Directories (~/.ipatool) ---
MAC = '94659C755502'
IPATOOL_DIR = os.path.expanduser(r'~\\.ipatool')
COOKIE_PATH = os.path.join(IPATOOL_DIR, 'cookies')
ACCOUNT_PATH = os.path.join(IPATOOL_DIR, 'account')

def load_settings():
    defaults = {
        'keychain_passphrase': '2211',
        'download_dir': BASE_DIR
    }
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # If old hardcoded path C:\DRIVERS was saved, migrate it to current BASE_DIR
                if data.get('download_dir') in [r'C:\DRIVERS', 'C:/DRIVERS', r'C:\DRIVERS\\']:
                    data['download_dir'] = BASE_DIR
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

def get_keychain_passphrase():
    return SETTINGS.get('keychain_passphrase', '2211')

def get_download_dir():
    d = SETTINGS.get('download_dir', BASE_DIR)
    if not d or not os.path.exists(d):
        return BASE_DIR
    return d
