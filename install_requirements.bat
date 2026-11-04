@echo off
chcp 65001 >nul
title تثبيت مكتبات ipatool-downloader
color 0b

where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo [خطأ] لم يتم العثور على Python في النظام!
    echo يرجى تثبيت Python 3 وتفعيل خيار Add Python to PATH.
    pause
    exit /b 1
)

python "%~dp0install_requirements.py"
if %ERRORLEVEL% NEQ 0 (
    color 0c
    pause
    exit /b %ERRORLEVEL%
)

color 0a
pause
