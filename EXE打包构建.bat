@echo off
REM === XianyuAutoReply EXE Build Script (One-Click) ===
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   XianyuAutoReply - One-Click Build
echo ============================================
echo.

REM --- Ask whether to skip frontend build ---
set SKIP_FRONTEND=0
choice /C YN /M "Skip frontend build (Y=skip, N=rebuild)"
if %errorlevel% equ 1 set SKIP_FRONTEND=1
echo.

REM --- Check python ---
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    goto :end
)

REM --- Check node/npm ---
call npm --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm not found, please install Node.js first.
    goto :end
)

REM --- Check Nuitka ---
python -c "import nuitka" 2>nul
if errorlevel 1 (
    echo [INFO] Installing Nuitka...
    pip install nuitka ordered-set zstandard
    if errorlevel 1 (
        echo [ERROR] Failed to install Nuitka.
        goto :end
    )
)

REM --- Read version from launcher/version.py ---
for /f %%a in ('python -c "from launcher.version import CURRENT_VERSION; print(CURRENT_VERSION)"') do set APP_VER=%%a
echo [INFO] Current version: v%APP_VER%
echo.

echo [1/6] Cleaning old build output...
if exist "build_output" (
    echo        Removing build_output...
    rmdir /s /q "build_output"
)
if exist "release" (
    echo        Removing release...
    rmdir /s /q "release"
)
mkdir release 2>nul
echo        Done.

if %SKIP_FRONTEND% equ 1 goto :skip_frontend

echo [2/6] Building frontend...
cd frontend
call npm ci --no-audit --no-fund
if errorlevel 1 (
    echo [ERROR] npm ci failed.
    cd ..
    goto :end
)
call npm run build
if errorlevel 1 (
    echo [ERROR] npm run build failed.
    cd ..
    goto :end
)
cd ..

if not exist "frontend\dist\index.html" (
    echo [ERROR] Frontend build output not found.
    goto :end
)
echo [INFO] Frontend build complete.
goto :after_frontend

:skip_frontend
echo [2/6] Skipping frontend build.
if not exist "frontend\dist\index.html" (
    echo [ERROR] frontend\dist not found. Run full build first.
    goto :end
)

:after_frontend

echo [3/6] Nuitka compiling launcher (may take several minutes)...
python -m nuitka ^
    --standalone ^
    --windows-console-mode=disable ^
    --windows-company-name=XianyuAutoReply ^
    --windows-product-name=XianyuAutoReply ^
    --windows-product-version=%APP_VER%.0 ^
    --windows-file-version=%APP_VER%.0 ^
    --output-filename=XianyuAutoReply.exe ^
    --output-dir=build_output ^
    --include-package=launcher ^
    --include-package=common ^
    --include-package=http ^
    --include-package=urllib ^
    --include-package=email ^
    --include-package=playwright ^
    --include-package-data=playwright ^
    --include-package=patchright ^
    --include-package-data=patchright ^
    --include-package=uvicorn ^
    --include-package=fastapi ^
    --include-package=sqlalchemy ^
    --include-package=pydantic ^
    --include-package=pydantic_settings ^
    --include-package=email_validator ^
    --include-package=asyncmy ^
    --include-package=pymysql ^
    --include-package=redis ^
    --include-package=aiohttp ^
    --include-package=aiohttp_socks ^
    --include-package=httpx ^
    --include-package=httpcore ^
    --include-package=loguru ^
    --include-package=passlib ^
    --include-package=jose ^
    --include-package=Crypto ^
    --include-package=websockets ^
    --include-package=multipart ^
    --include-package=PIL ^
    --include-package=anyio ^
    --include-package=starlette ^
    --include-package=click ^
    --include-package=h11 ^
    --include-package=sniffio ^
    --include-package=idna ^
    --include-package=certifi ^
    --include-package=dateutil ^
    --include-package=apscheduler ^
    --include-package=python_socks ^
    --include-package=requests ^
    --include-package=pandas ^
    --include-package=openpyxl ^
    --include-package=qrcode ^
    --include-package=openai ^
    --include-package=bcrypt ^
    --nofollow-import-to=test ^
    --nofollow-import-to=tests ^
    --nofollow-import-to=docs ^
    --nofollow-import-to=setuptools ^
    --nofollow-import-to=pip ^
    --nofollow-import-to=wheel ^
    --nofollow-import-to=nuitka ^
    --nofollow-import-to=pandas.tests ^
    --nofollow-import-to=sqlalchemy.testing ^
    --nofollow-import-to=passlib.tests ^
    --nofollow-import-to=Crypto.SelfTest ^
    --nofollow-import-to=qrcode.tests ^
    --nofollow-import-to=PyInstaller ^
    --nofollow-import-to=pygments ^
    --nofollow-import-to=pydoc ^
    --nofollow-import-to=doctest ^
    --nofollow-import-to=unittest ^
    --enable-plugin=tk-inter ^
    --assume-yes-for-downloads launcher\main.py
if errorlevel 1 (
    echo.
    echo [ERROR] Nuitka compile failed, check errors above.
    goto :end
)

echo [4/6] Copying project files to dist...
set DIST_DIR=build_output\main.dist

REM --- Copy sub-service source and common ---
xcopy /E /I /Y "backend-web" "%DIST_DIR%\backend-web" >nul
xcopy /E /I /Y "websocket" "%DIST_DIR%\websocket" >nul
xcopy /E /I /Y "scheduler" "%DIST_DIR%\scheduler" >nul
xcopy /E /I /Y "common" "%DIST_DIR%\common" >nul
xcopy /E /I /Y "frontend\dist" "%DIST_DIR%\frontend\dist" >nul

REM --- Copy pythonw.exe to dist dir (used for launching sub-services without console window) ---
for %%P in (python.exe) do (
    set "PYTHON_DIR=%%~dp$PATH:P"
)
if not exist "%DIST_DIR%\python.exe" (
    if exist "%PYTHON_DIR%python.exe" (
        copy /Y "%PYTHON_DIR%python.exe" "%DIST_DIR%\python.exe" >nul
        echo [INFO] Copied python.exe to dist dir
    ) else (
        echo [WARN] python.exe not found, Playwright fallback install may fail
    )
)
if not exist "%DIST_DIR%\pythonw.exe" (
    if exist "%PYTHON_DIR%pythonw.exe" (
        copy /Y "%PYTHON_DIR%pythonw.exe" "%DIST_DIR%\pythonw.exe" >nul
        echo [INFO] Copied pythonw.exe to dist dir
    ) else (
        echo [WARN] pythonw.exe not found, sub-services may show console windows
    )
)

REM --- Copy Python standard library so standalone python.exe can work ---
REM    python.exe needs at least encodings module to start. Copy the Lib
REM    directory from the build machine's Python installation.
if defined PYTHON_DIR (
    if not exist "%DIST_DIR%\Lib\encodings" (
        if exist "%PYTHON_DIR%Lib" (
            echo [INFO] Copying Python standard library...
            xcopy /E /I /Y /Q "%PYTHON_DIR%Lib" "%DIST_DIR%\Lib" >nul
            echo [INFO] Python standard library copied to dist dir
        ) else (
            echo [WARN] Python Lib dir not found at %PYTHON_DIR%Lib, standalone python.exe may fail
        )
    )
)
set "PACKAGED_BROWSER_DIR=%DIST_DIR%\ms-playwright"
mkdir "%PACKAGED_BROWSER_DIR%" 2>nul
set "PLAYWRIGHT_BROWSERS_PATH=%PACKAGED_BROWSER_DIR%"
echo [INFO] Installing Chromium into package dir...
python -m playwright install chromium
if errorlevel 1 (
    echo [ERROR] Failed to bundle Chromium browser.
    goto :end
)
python -m patchright install chromium
if errorlevel 1 (
    echo [ERROR] Failed to bundle Patchright Chromium browser.
    goto :end
)

REM --- Clean temp files from copies ---
if exist "%DIST_DIR%\backend-web\logs" rmdir /s /q "%DIST_DIR%\backend-web\logs"
if exist "%DIST_DIR%\websocket\logs" rmdir /s /q "%DIST_DIR%\websocket\logs"
if exist "%DIST_DIR%\scheduler\logs" rmdir /s /q "%DIST_DIR%\scheduler\logs"
if exist "%DIST_DIR%\backend-web\.env" del /f "%DIST_DIR%\backend-web\.env"
if exist "%DIST_DIR%\websocket\.env" del /f "%DIST_DIR%\websocket\.env"
if exist "%DIST_DIR%\scheduler\.env" del /f "%DIST_DIR%\scheduler\.env"
if exist "%DIST_DIR%\backend-web\.env.example" del /f "%DIST_DIR%\backend-web\.env.example"
if exist "%DIST_DIR%\websocket\.env.example" del /f "%DIST_DIR%\websocket\.env.example"
if exist "%DIST_DIR%\scheduler\.env.example" del /f "%DIST_DIR%\scheduler\.env.example"
if exist "%DIST_DIR%\backend-web\pyproject.toml" del /f "%DIST_DIR%\backend-web\pyproject.toml"
if exist "%DIST_DIR%\websocket\pyproject.toml" del /f "%DIST_DIR%\websocket\pyproject.toml"
if exist "%DIST_DIR%\scheduler\pyproject.toml" del /f "%DIST_DIR%\scheduler\pyproject.toml"
if exist "%DIST_DIR%\backend-web\static\uploads" rmdir /s /q "%DIST_DIR%\backend-web\static\uploads"
if exist "%DIST_DIR%\websocket\static\uploads" rmdir /s /q "%DIST_DIR%\websocket\static\uploads"
if exist "%DIST_DIR%\scheduler\static\uploads" rmdir /s /q "%DIST_DIR%\scheduler\static\uploads"
if exist "%DIST_DIR%\websocket\browser_data" rmdir /s /q "%DIST_DIR%\websocket\browser_data"
for %%D in ("%DIST_DIR%\backend-web" "%DIST_DIR%\websocket" "%DIST_DIR%\scheduler" "%DIST_DIR%\common") do (
    for /d /r "%%~fD" %%C in (__pycache__) do (
        if exist "%%~fC" rmdir /s /q "%%~fC"
    )
    del /s /q "%%~fD\*.pyc" 2>nul
    del /s /q "%%~fD\*.pyo" 2>nul
    if exist "%%~fD\.pytest_cache" rmdir /s /q "%%~fD\.pytest_cache"
    if exist "%%~fD\.mypy_cache" rmdir /s /q "%%~fD\.mypy_cache"
    if exist "%%~fD\temp" rmdir /s /q "%%~fD\temp"
    if exist "%%~fD\tmp" rmdir /s /q "%%~fD\tmp"
)

echo [5/6] Moving to release dir...
python "%~dp0scripts\copy_with_progress.py" "%DIST_DIR%" "release\XianyuAutoReply"
if errorlevel 1 (
    echo [INFO] Fallback to xcopy...
    xcopy /E /I /Y "%DIST_DIR%" "release\XianyuAutoReply" >nul
)
if not exist "release\XianyuAutoReply\logs" mkdir "release\XianyuAutoReply\logs" >nul
REM --- Copy compiled EXE into release dir to match the dist contents ---
if exist "build_output\XianyuAutoReply.exe" (
    copy /Y "build_output\XianyuAutoReply.exe" "release\XianyuAutoReply\XianyuAutoReply.exe" >nul
    echo [INFO] Copied EXE to release dir
) else (
    echo [WARN] Compiled EXE not found at build_output\XianyuAutoReply.exe
)

REM --- Remove data dir from release (user data should not be packaged) ---
if exist "release\XianyuAutoReply\data" rmdir /s /q "release\XianyuAutoReply\data"

echo [6/6] Packaging release zip...
set ZIP_NAME=app-v%APP_VER%.zip
if exist "release\%ZIP_NAME%" del /f "release\%ZIP_NAME%"

echo        Source: %CD%\release\XianyuAutoReply
echo        Target: %CD%\release\%ZIP_NAME%

REM --- Compress: prefer 7-Zip (fast, multi-threaded), fallback to Python zipfile (stored mode) ---
set ZIP_OK=0
where 7z >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] Using 7-Zip for fast compression...
    7z a -tzip -mx=1 -mmt=on "release\%ZIP_NAME%" ".\release\XianyuAutoReply\*"
    if not errorlevel 1 set ZIP_OK=1
)

if %ZIP_OK% equ 0 (
    echo [INFO] Using Python zipfile...
    python "%~dp0scripts\zip_with_progress.py" "%CD%\release\XianyuAutoReply" "%CD%\release\%ZIP_NAME%"
)

if not exist "release\%ZIP_NAME%" (
    echo [INFO] Fallback to PowerShell Compress-Archive...
    powershell -Command "Compress-Archive -Path 'release\XianyuAutoReply\*' -DestinationPath 'release\%ZIP_NAME%' -Force"
)

if not exist "release\%ZIP_NAME%" (
    echo [ERROR] Failed to create zip package.
    goto :end
)

echo.
echo ============================================
echo   Build Complete!
echo   Output: release\XianyuAutoReply\
echo   Zip:    release\%ZIP_NAME%
echo   Run:    release\XianyuAutoReply\XianyuAutoReply.exe
echo ============================================
echo.
echo Notes:
echo   1. Release dir contains Python source code (.py)
echo   2. Launcher is compiled to native C code by Nuitka
echo   3. Send release\XianyuAutoReply folder to users
echo   4. release\%ZIP_NAME% can be uploaded to update server
echo.

:end
echo.
echo Press any key to exit...
pause >nul
