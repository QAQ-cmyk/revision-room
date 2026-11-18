@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "runtime\python.exe" goto source
"runtime\python.exe" launch.py %*
exit /b %errorlevel%
:source
where py >nul 2>&1
if errorlevel 1 goto try_python
py -3 -c "import sys; raise SystemExit(sys.version_info < (3, 11))" >nul 2>&1
if errorlevel 1 goto try_python
echo 正在打开修订室...
py -3 launch.py %*
exit /b
:try_python
python -c "import sys; raise SystemExit(sys.version_info < (3, 11))" >nul 2>&1
if errorlevel 1 goto missing
echo 正在打开修订室...
python launch.py %*
exit /b
:missing
echo 请先安装 Python 3.11 或更新版本，并勾选 Add Python to PATH。
echo 安装后重新打开本文件。下载地址：https://www.python.org/downloads/windows/
pause
