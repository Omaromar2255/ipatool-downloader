import os
import json
import time
import threading
from .config import SAVED_QUEUE_FILE, get_download_dir

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
