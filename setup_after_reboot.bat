@echo off
echo ========================================
echo WSL2 + OpenWrt Build Environment Setup
echo ========================================
echo.

echo [1/4] Setting WSL default version to 2...
wsl --set-default-version 2
if %errorlevel% neq 0 (
    echo Downloading WSL2 kernel update...
    powershell -Command "Invoke-WebRequest -Uri 'https://wslstorestorage.blob.core.windows.net/wslblob/wsl_update_x64.msi' -OutFile '%TEMP%\wsl_update.msi'"
    msiexec /i "%TEMP%\wsl_update.msi" /quiet
    wsl --set-default-version 2
)

echo.
echo [2/4] Installing Ubuntu 22.04...
wsl --install -d Ubuntu-22.04 --no-launch
if %errorlevel% neq 0 (
    echo Trying alternative install...
    winget install Canonical.Ubuntu.2204
)

echo.
echo [3/4] Launching Ubuntu setup (create user when prompted)...
echo ВАЖНО: Создайте имя пользователя и пароль когда Ubuntu запустится!
echo После создания - закройте Ubuntu и нажмите любую клавишу...
wsl -d Ubuntu-22.04
pause

echo.
echo [4/4] Running OpenWrt build setup in WSL...
wsl -d Ubuntu-22.04 -- bash /mnt/c/Users/Nikita/Downloads/openwrt-ra82-main/wsl_build_setup.sh

echo.
echo ========================================
echo Done! Check above for any errors.
echo ========================================
pause
