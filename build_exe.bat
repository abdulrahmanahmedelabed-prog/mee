@echo off
REM Build a standalone Windows version (no Python needed on the shop PC)
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --windowed --name ShopAccounting main.py
echo.
echo Done. The program is in dist\ShopAccounting
pause
