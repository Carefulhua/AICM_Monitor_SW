@echo off
rem ==============================================================
rem  AICM-NT400 DVtest monitor - One-click Windows build script
rem  Builds dist\AICM-NT4K DV监控界面\ via PyInstaller (onedir).
rem  Uses Anaconda Python 3.12 (conda channel, PyQt5/PyInstaller pre-installed).
rem  Run ONLY from a NATIVE Windows command prompt (not WSL).
rem ==============================================================

rem ---- 1. Fix PATH so PyInstaller can find Anaconda DLLs (python312.dll, vcruntime, ucrtbase, zlib) ----
rem     Without this, PyInstaller runs into error 126: "The specified module could not be found."
set "CONDA_LIBBIN=C:\ProgramData\anaconda3\Library\bin"
set "PATH=%CONDA_LIBBIN%;%PATH%"

rem ---- 2. Set Python interpreter ----
set "PY=C:\ProgramData\anaconda3\python.exe"
if not exist "%PY%" (
    echo [ERROR] Anaconda python.exe not found at %PY%
    pause
    exit /b 1
)

rem ---- 3. Install/build dependencies (conda packages, pip deps from TUNA) ----
echo [1/3] Installing PyQt5 (pip, TUNA mirror)...
"%PY%" -m pip install --user -i https://pypi.tuna.tsinghua.edu.cn/simple --upgrade PyQt5
if errorlevel 1 (
    echo [ERROR] PyQt5 install failed.
    pause
    exit /b 1
)

echo [2/3] Installing pyqtgraph (pip, TUNA mirror)...
"%PY%" -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple pyqtgraph
if errorlevel 1 (
    echo [ERROR] pyqtgraph install failed.
    pause
    exit /b 1
)

rem  Pin numpy to conda-compatible version (OpenBLAS, no MKL bloat)
echo [3/3] Installing numpy...
"%PY%" -m pip install --user -i https://pypi.tuna.tsinghua.edu.cn/simple --upgrade "numpy==1.26.4"
if errorlevel 1 (
    echo [ERROR] numpy install failed.
    pause
    exit /b 1
)

rem ---- 4. Verify dependencies loaded OK ----
"%PY%" -c "import PyQt5.QtCore, PyQt5.QtWidgets, pyqtgraph, numpy, PyInstaller" 2>&1
if errorlevel 1 (
    echo [ERROR] Missing a build dependency.
    echo Run: %PY% -c "import PyQt5, pyqtgraph, numpy, PyInstaller"
    pause
    exit /b 1
)

rem ---- 5. Build with PyInstaller (onedir mode: produces dist\can_monitor\ folder) ----
echo [4/4] Building with PyInstaller (onedir, may take 2-5 minutes)...
"%PY%" -m PyInstaller can_monitor.spec --noconfirm --clean
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed. See messages above.
    pause
    exit /b 1
)

echo.
echo Done: dist\AICM-NT4K DV监控界面\AICM-NT4K DV监控界面.exe
echo       (Plus _internal resources folder - copy the whole folder to target machine)
echo .
rem Keep console open so user can see the result
pause