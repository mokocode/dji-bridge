@echo off
title DJI FPV Controller 2 - Setup
echo.
echo  ╔═══════════════════════════════════════════════════╗
echo  ║  DJI FPV Controller 2 → vJoy Bridge — Setup      ║
echo  ╚═══════════════════════════════════════════════════╝
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    py --version >nul 2>&1
    if not errorlevel 1 (
        doskey python=py $*
        echo  [OK] Python (py launcher) found
    ) else (
        echo  [!] Python is not installed on your system.
        echo  [..] Attempting to install Python automatically...
        echo.
        
        set "PY_INSTALLED=0"
        
        :: Method 1: Try winget if available
        where winget >nul 2>&1
        if not errorlevel 1 (
            echo  [..] Installing Python via winget (Python 3.11)...
            winget install --id Python.Python.3.11 --exact --source winget --accept-package-agreements --accept-source-agreements --silent
            if not errorlevel 1 set "PY_INSTALLED=1"
        )
        
        :: Method 2: If winget failed or not available, download official installer via curl or powershell
        if "!PY_INSTALLED!"=="0" (
            set "PY_INSTALLER=%TEMP%\python-3.11.9-amd64.exe"
            set "PY_URL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
            echo  [..] Downloading Python 3.11 installer from python.org...
            where curl.exe >nul 2>&1
            if not errorlevel 1 (
                curl.exe -L -o "%TEMP%\python-3.11.9-amd64.exe" "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
            ) else (
                powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe', '%TEMP%\python-3.11.9-amd64.exe')"
            )
            
            if exist "%TEMP%\python-3.11.9-amd64.exe" (
                echo  [..] Running Python installer (installing for all users + adding to PATH)...
                "%TEMP%\python-3.11.9-amd64.exe" /passive InstallAllUsers=1 PrependPath=1 Include_pip=1 Include_test=0
                set "PY_INSTALLED=1"
            )
        )
        
        :: Refresh PATH for current session
        for /f "tokens=2*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYS_PATH=%%b"
        for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USER_PATH=%%b"
        set "PATH=%SYS_PATH%;%USER_PATH%;%PATH%"
        if exist "%LOCALAPPDATA%\Programs\Python\Python311" set "PATH=%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%PATH%"
        if exist "C:\Program Files\Python311" set "PATH=C:\Program Files\Python311;C:\Program Files\Python311\Scripts;%PATH%"
        
        :: Verify python after installation
        python --version >nul 2>&1
        if errorlevel 1 (
            py --version >nul 2>&1
            if errorlevel 1 (
                echo.
                echo  [!] Python was installed but the command line session needs a restart to pick up PATH.
                echo      Please close this window and run SETUP.bat again.
                echo      Or download manually from https://python.org (check 'Add to PATH').
                echo.
                pause
                exit /b 1
            )
        )
        echo  [OK] Python installed successfully!
    )
) else (
    echo  [OK] Python found
)

:: Install dependencies
echo  [..] Installing Python packages...
python -m pip install --upgrade pip --quiet >nul 2>&1
python -m pip install -r "%~dp0requirements.txt" --quiet
if errorlevel 1 (
    pip install -r "%~dp0requirements.txt" --quiet
    if errorlevel 1 (
        echo  [X] Failed to install packages
        pause
        exit /b 1
    )
)
echo  [OK] Python packages installed

:: Check vJoy
set "VJOY_INSTALLED=0"
if exist "C:\Program Files\vJoy\x64\vJoyInterface.dll" set "VJOY_INSTALLED=1"
if exist "C:\Program Files\vJoy\vJoyInterface.dll" set "VJOY_INSTALLED=1"

if "%VJOY_INSTALLED%"=="1" (
    echo  [OK] vJoy driver already installed
) else (
    echo.
    echo  [!] vJoy driver not detected on your system.
    if exist "%~dp0vJoySetup_v2.2.2.0_Win10_Win11.exe" (
        echo  [..] Starting vJoy installer (vJoySetup_v2.2.2.0_Win10_Win11.exe)...
        echo       Please follow the setup wizard prompts to complete installation.
        start /wait "" "%~dp0vJoySetup_v2.2.2.0_Win10_Win11.exe"
        
        :: Re-check after installation
        if exist "C:\Program Files\vJoy\x64\vJoyInterface.dll" set "VJOY_INSTALLED=1"
        if exist "C:\Program Files\vJoy\vJoyInterface.dll" set "VJOY_INSTALLED=1"
        
        if "!VJOY_INSTALLED!"=="1" (
            echo  [OK] vJoy driver installed successfully
        ) else if exist "C:\Program Files\vJoy\x64\vJoyInterface.dll" (
            echo  [OK] vJoy driver installed successfully
        ) else if exist "C:\Program Files\vJoy\vJoyInterface.dll" (
            echo  [OK] vJoy driver installed successfully
        ) else (
            echo  [!] vJoy installation was not completed or needs a reboot.
        )
    ) else (
        echo  [X] vJoy installer not found in folder.
        echo      Download from: https://github.com/njz3/vJoy/releases
    )
    echo.
    echo  IMPORTANT: Open "Configure vJoy" from your Start menu and set up Device #1:
    echo    - Check ALL 8 axes (X, Y, Z, Rx, Ry, Rz, Slider, Dial)
    echo    - Set buttons to 16
    echo    - Click Apply
    echo.
)

echo.
echo  ═══════════════════════════════════════════════════
echo   Setup complete! Next steps:
echo.
echo   1. Plug in your DJI FPV Controller 2 via USB-C
echo   2. Power it on (tap once, then hold power button)
echo   3. Run DETECT.bat to verify your axis numbers
echo   4. Run BRIDGE.bat to start the bridge
echo   5. In Wardogs: Settings → HOTAS → select "vJoy Device"
echo  ═══════════════════════════════════════════════════
echo.
pause
