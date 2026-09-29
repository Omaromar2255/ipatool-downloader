@echo off
if "%~1"=="" (
    echo Usage: download.bat ^<bundle_id or app_name^> [output_file.ipa] [passphrase]
    echo Example: download.bat com.google.ios.youtube YouTube.ipa 2211
    exit /b 1
)

python "%~dp0ipatool-download.py" %*
