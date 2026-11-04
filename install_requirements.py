#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
اسكربت فحص وتثبيت المكتبات المطلوبة لمشروع ipatool-downloader
"""

import sys
import subprocess
import os

# Reconfigure stdout/stderr to UTF-8 so Arabic and symbols never fail on Windows consoles
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REQUIRED_PACKAGES = [
    ("requests", "requests>=2.28.0"),
    ("PIL", "Pillow>=10.0.0"),
    ("cryptography", "cryptography>=41.0.0"),
]

def check_package(module_name):
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False

def install_packages():
    print("=" * 60)
    print("   فحص وتثبيت المكتبات المطلوبة لمشروع ipatool-downloader")
    print("=" * 60)
    print(f"إصدار Python الحالي: {sys.version.split()[0]}\n")

    missing = []
    for module_name, pkg_spec in REQUIRED_PACKAGES:
        if check_package(module_name):
            print(f"  [✓] المكتبة {module_name:<15} مثبتة بالفعل.")
        else:
            print(f"  [✗] المكتبة {module_name:<15} غير مثبتة (المطلوب: {pkg_spec}).")
            missing.append(pkg_spec)

    req_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements.txt")

    if not missing:
        print("\nجميع المكتبات المطلوبة مثبتة مسبقاً وتعمل بشكل سليم!")
        return 0

    print(f"\nجاري تثبيت المكتبات الناقصة: {', '.join(missing)} ...\n")
    try:
        cmd = [sys.executable, "-m", "pip", "install"]
        if os.path.exists(req_file):
            cmd.extend(["-r", req_file])
        else:
            cmd.extend(missing)

        subprocess.check_call(cmd)
        print("\n" + "=" * 60)
        print("   تم تثبيت جميع المكتبات بنجاح!")
        print("=" * 60)
        return 0
    except subprocess.CalledProcessError as e:
        print(f"\n[خطأ] فشل التثبيت برمز خطأ: {e.returncode}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(install_packages())
