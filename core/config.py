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
PURCHASES_CACHE_FILE = os.path.join(BASE_DIR, 'purchases_cache.json')
DEFAULT_DOWNLOAD_DIR = os.path.join(BASE_DIR, 'downloads')

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
        'download_dir': DEFAULT_DOWNLOAD_DIR
    }
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                saved_dir = data.get('download_dir')
                # If old hardcoded path C:\DRIVERS or BASE_DIR itself was saved, migrate it to DEFAULT_DOWNLOAD_DIR
                if not saved_dir or saved_dir in [r'C:\DRIVERS', 'C:/DRIVERS', r'C:\DRIVERS\\', BASE_DIR]:
                    data['download_dir'] = DEFAULT_DOWNLOAD_DIR
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
    d = SETTINGS.get('download_dir')
    if not d or d == BASE_DIR:
        d = DEFAULT_DOWNLOAD_DIR
    elif not os.path.isabs(d):
        d = os.path.normpath(os.path.join(BASE_DIR, d))
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d

def set_download_dir(path):
    if not path or path == BASE_DIR:
        path = DEFAULT_DOWNLOAD_DIR
    elif not os.path.isabs(path):
        path = os.path.normpath(os.path.join(BASE_DIR, path))
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
    SETTINGS['download_dir'] = path
    save_settings(SETTINGS)
    return path
