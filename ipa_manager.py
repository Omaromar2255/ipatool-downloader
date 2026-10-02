"""
مدير تطبيقات IPA (IPA Tool Downloader & Manager)
النسخة المقسمة والمنظمة معمارياً (Modular Architecture)
"""

import sys
import os
import tkinter as tk

# Core Modules Re-exports (Backward Compatibility)
from core.config import (
    SETTINGS_FILE,
    load_settings,
    save_settings,
    SETTINGS,
    MAC,
    COOKIE_PATH,
    ACCOUNT_PATH,
    IPATOOL_DIR,
    IPATOOL_PATH,
    CACHE_FILE,
    SAVED_QUEUE_FILE,
    get_keychain_passphrase,
    get_download_dir
)
from core.cache import (
    VERSIONS_CACHE,
    load_cache,
    save_cache,
    get_cached_version,
    set_cached_version
)
from core.queue_manager import (
    load_saved_queue,
    save_saved_queue,
    add_to_saved_queue,
    remove_from_saved_queue,
    update_saved_queue_item
)
from core.apple_api import (
    session,
    check_auth_status,
    perform_login,
    perform_revoke,
    get_cookies,
    get_apple_headers,
    generate_download_cmd,
    search_app,
    get_latest_ext_id,
    get_all_version_ids,
    BufferedRemoteZipReader,
    get_version_info,
    download_ipa
)
from core.utils import (
    parse_os,
    is_os_le,
    format_size,
    setup_entry_clipboard
)
from ui.main_window import IPAManagerApp

def main():
    root = tk.Tk()
    app = IPAManagerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
