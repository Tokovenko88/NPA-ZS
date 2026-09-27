@echo off
chcp 65001 >nul 2>&1
set REPO=%~dp0..
cd /d "%REPO%"

echo Checking FreeDeepseekAPI proxy on port 9655...

netstat -an 2>nul | findstr /R "9655" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Proxy already running at http://127.0.0.1:9655
    goto :eof
)

echo Starting FreeDeepseekAPI proxy...
echo Logs: data\logs\free-deepseek-proxy.log
rem Antivirus HTTPS interception (Kaspersky/Dr.Web/ESET) breaks Node TLS: export the
rem Windows trusted roots into a PEM bundle and pass it via NODE_EXTRA_CA_CERTS.
rem The variable is read at process start, so it must be set here, not in .env.
set "CA_PEM="
if exist "%~dp0export_system_ca.ps1" for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0export_system_ca.ps1" -Quiet 2^>nul`) do set "CA_PEM=%%P"
if defined CA_PEM set "NODE_EXTRA_CA_CERTS=%CA_PEM%"
set NON_INTERACTIVE=1
start "" /min /B cmd /c "cd /d tools\FreeDeepseekAPI && npm start"
timeout /t 3 /nobreak >nul 2>&1

netstat -an 2>nul | findstr /R "9655" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Proxy running at http://127.0.0.1:9655
) else (
    echo Check logs: data\logs\free-deepseek-proxy.log
)
