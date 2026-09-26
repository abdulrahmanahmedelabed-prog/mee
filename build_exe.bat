@echo off
REM Build the Windows version for customers (no Python needed on the shop PC)
REM 1) Edit core\vendor.py with your name and WhatsApp number
REM 2) Run once: python tools\license_tool.py init   (keeps your private key in %USERPROFILE%\.shop_license)
if not exist core\license_pubkey.py (
  echo [!] License keys not generated yet. Run: python tools\license_tool.py init
  pause
  exit /b 1
)
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --windowed --name ShopAccounting --hidden-import core.license_pubkey main.py
echo.
echo Done. The program is in dist\ShopAccounting  (copy the whole folder to the shop PC)
echo Do NOT ship the tools folder or your private key.
pause
