import os
import json
import threading
from .config import CACHE_FILE, PURCHASES_CACHE_FILE

# --- Thread-Safe Cache ---
cache_lock = threading.Lock()
VERSIONS_CACHE = {}
PURCHASES_CACHE = []

def load_purchases_cache():
    global PURCHASES_CACHE
    with cache_lock:
        if os.path.exists(PURCHASES_CACHE_FILE):
            try:
                with open(PURCHASES_CACHE_FILE, 'r', encoding='utf-8') as f:
                    PURCHASES_CACHE = json.load(f)
            except Exception:
                PURCHASES_CACHE = []
        else:
            PURCHASES_CACHE = []
    return list(PURCHASES_CACHE)

def save_purchases_cache(purchases_list):
    global PURCHASES_CACHE
    with cache_lock:
        PURCHASES_CACHE = list(purchases_list)
        try:
            with open(PURCHASES_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(purchases_list, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

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
