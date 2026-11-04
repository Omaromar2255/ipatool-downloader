"""
core/image_loader.py
وحدة تحميل ومعالجة وتخزين أيقونات التطبيقات (App Icon Loader & Cache)
المميزات:
- تخزين مؤقت في الذاكرة (In-Memory Cache)
- تخزين مؤقت على القرص في .cache/icons (Disk Cache)
- قص زوايا دائرية ناعمة بنمط iOS (Super-sampled Rounded Corners)
- تحميل متوازي غير تزامني بدون تجميد الواجهة (Async ThreadPool)
- أيقونة افتراضية ناعمة (Placeholder Icon)
"""

import os
import io
import hashlib
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw, ImageTk

from core.config import BASE_DIR

ICON_CACHE_DIR = os.path.join(BASE_DIR, '.cache', 'icons')
try:
    os.makedirs(ICON_CACHE_DIR, exist_ok=True)
except Exception:
    pass

_MEMORY_CACHE = {}
_LOCK = threading.Lock()
_EXECUTOR = ThreadPoolExecutor(max_workers=6)

def _get_cache_path(url):
    url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()
    return os.path.join(ICON_CACHE_DIR, f"{url_hash}.png")

def make_rounded_icon(pil_img, size=(56, 56), radius=None):
    """قص الصورة بزوايا دائرية فائقة النعومة بنمط iOS"""
    if radius is None:
        radius = max(6, int(size[0] * 0.22))

    # تغيير الحجم بجودة عالية
    img = pil_img.convert("RGBA").resize(size, Image.Resampling.LANCZOS)

    # قناع فائق الدقة (4x Super-sampling) لمنع التعرج الحوافي
    scale = 4
    mask_size = (size[0] * scale, size[1] * scale)
    mask = Image.new("L", mask_size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle(
        [(0, 0), (mask_size[0] - 1, mask_size[1] - 1)],
        radius=radius * scale,
        fill=255
    )
    mask = mask.resize(size, Image.Resampling.LANCZOS)

    rounded = Image.new("RGBA", size, (0, 0, 0, 0))
    rounded.paste(img, (0, 0), mask=mask)
    return rounded

def get_placeholder_photo(size=(56, 56), radius=None, bg_color="#313244", fg_color="#89b4fa"):
    """إنشاء أيقونة افتراضية أنيقة تناسب الثيم الداكن"""
    if radius is None:
        radius = max(6, int(size[0] * 0.22))

    key = ("__placeholder__", size[0], size[1], radius, bg_color, fg_color)
    with _LOCK:
        if key in _MEMORY_CACHE:
            return _MEMORY_CACHE[key]

    scale = 4
    mask_size = (size[0] * scale, size[1] * scale)
    mask = Image.new("L", mask_size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle(
        [(0, 0), (mask_size[0] - 1, mask_size[1] - 1)],
        radius=radius * scale,
        fill=255
    )
    mask = mask.resize(size, Image.Resampling.LANCZOS)

    base = Image.new("RGBA", size, bg_color)
    d = ImageDraw.Draw(base)

    # رسم إطار رمز التطبيق الداخلي
    w, h = size
    pad = max(4, int(w * 0.25))
    d.rounded_rectangle(
        [(pad, pad), (w - pad - 1, h - pad - 1)],
        radius=max(3, radius // 2),
        outline=fg_color,
        width=max(1, int(w * 0.035))
    )

    out = Image.new("RGBA", size, (0, 0, 0, 0))
    out.paste(base, (0, 0), mask=mask)

    photo = ImageTk.PhotoImage(out)
    with _LOCK:
        _MEMORY_CACHE[key] = photo
    return photo

def load_app_icon_async(icon_url, root, size=(56, 56), radius=None, on_loaded_callback=None):
    """
    تحميل أيقونة التطبيق بشكل غير تزامني.
    يعيد الأيقونة المخزنة فوراً إن وجدت، أو يعيد الأيقونة الافتراضية
    ويبدأ التنزيل والمعالجة في خيط منفصل مع استدعاء on_loaded_callback عند الانتهاء.
    """
    if radius is None:
        radius = max(6, int(size[0] * 0.22))

    key = (icon_url, size[0], size[1], radius)
    with _LOCK:
        if icon_url and key in _MEMORY_CACHE:
            return _MEMORY_CACHE[key]

    placeholder = get_placeholder_photo(size, radius)
    if not icon_url:
        return placeholder

    cache_file = _get_cache_path(icon_url)

    # فحص القرص أولاً
    if os.path.exists(cache_file):
        try:
            pil_img = Image.open(cache_file)
            rounded = make_rounded_icon(pil_img, size, radius)
            photo = ImageTk.PhotoImage(rounded)
            with _LOCK:
                _MEMORY_CACHE[key] = photo
            return photo
        except Exception:
            pass

    # تحميل في الخلفية
    def worker():
        try:
            req = urllib.request.Request(icon_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=8) as res:
                data = res.read()

            pil_img = Image.open(io.BytesIO(data))
            # حفظ في القرص
            try:
                pil_img.save(cache_file, format="PNG")
            except Exception:
                pass

            rounded = make_rounded_icon(pil_img, size, radius)

            def on_main_thread():
                try:
                    photo = ImageTk.PhotoImage(rounded)
                    with _LOCK:
                        _MEMORY_CACHE[key] = photo
                    if on_loaded_callback:
                        on_loaded_callback(photo)
                except Exception:
                    pass

            if root:
                root.after(0, on_main_thread)
        except Exception:
            pass

    _EXECUTOR.submit(worker)
    return placeholder
