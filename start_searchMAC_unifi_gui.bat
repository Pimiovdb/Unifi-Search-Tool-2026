@echo off
cd /d "%~dp0"

py -c "import requests" >nul 2>nul
if errorlevel 1 (
    echo requests is missing; installing from requirements_unifi_gui.txt...
    py -m pip install -r requirements_unifi_gui.txt
    if errorlevel 1 (
        echo Installation failed.
        pause
        exit /b 1
    )
)

py searchMAC_Unifi_GUI_ENG.pyw
