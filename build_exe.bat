@echo off
setlocal
cd /d "%~dp0"
REM Build the Windows version for customers (no Python needed on the shop PC)
REM 1) Edit core\vendor.py with your name and WhatsApp number
REM 2) Run once: python tools\license_tool.py init   (keeps your private key in %USERPROFILE%\.shop_license)
REM Easier alternative: GitHub -> Actions -> "Windows build (EXE + Setup)" builds it in the cloud.
if not exist core\license_pubkey.py (
  echo [!] License keys not generated yet. Run: python tools\license_tool.py init
  pause
  exit /b 1
)
python -m pip install -r requirements.txt pyinstaller || goto :fail

REM PyInstaller needs its launcher files (run.exe / runw.exe). Antivirus often deletes them.
python -c "import os,PyInstaller as p,sys; d=os.path.join(os.path.dirname(p.__file__),'bootloader','Windows-64bit-intel'); sys.exit(0 if os.path.exists(os.path.join(d,'runw.exe')) else 1)"
if errorlevel 1 (
  echo.
  echo [!] PyInstaller launcher runw.exe is missing - usually removed by Windows Defender / antivirus.
  echo     1^) Windows Security ^> Virus ^& threat protection ^> Protection history: restore/allow runw.exe
  echo        or add an exclusion for your Python folder and this project folder.
  echo     2^) Then reinstall:  python -m pip install --force-reinstall --no-cache-dir pyinstaller
  echo     Or use the cloud build: GitHub ^> Actions ^> "Windows build (EXE + Setup)".
  goto :fail
)

if exist build rmdir /s /q build
if exist dist\ShopAccounting rmdir /s /q dist\ShopAccounting
python -m PyInstaller --noconfirm --clean --windowed --name ShopAccounting --hidden-import core.license_pubkey --add-data "i18n;i18n" --add-data "docs;docs" main.py || goto :fail
if not exist dist\ShopAccounting\ShopAccounting.exe goto :fail

echo.
echo Done. The program is in dist\ShopAccounting  (copy the whole folder to the shop PC)
echo Optional installer: open installer\ShopAccounting.iss in Inno Setup and press Compile.
echo Do NOT ship the tools folder or your private key.
pause
exit /b 0

:fail
echo.
echo [X] BUILD FAILED - nothing usable in dist. Read the messages above.
pause
exit /b 1
