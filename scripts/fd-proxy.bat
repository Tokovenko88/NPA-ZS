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
set NON_INTERACTIVE=1
start "" /min /B cmd /c "cd /d tools\FreeDeepseekAPI && npm start"
timeout /t 3 /nobreak >nul 2>&1

netstat -an 2>nul | findstr /R "9655" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Proxy running at http://127.0.0.1:9655
) else (
    echo Check logs: data\logs\free-deepseek-proxy.log
)
