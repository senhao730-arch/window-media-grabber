$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed' }
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $taskPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
& $taskPython -m PyInstaller --noconfirm --onefile --windowed --name 窗口媒体抓取器_修复版 --icon assets\app-icon.ico --add-data 'assets;assets' --collect-all imageio_ffmpeg --collect-all windows_capture main.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
