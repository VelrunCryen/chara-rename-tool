@echo off
chcp 65001 >nul
cd /d "%~dp0"
python chara_gui.py
if errorlevel 1 pause