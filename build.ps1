$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

python -m pip install --upgrade pip
python -m pip install pyinstaller

if (Test-Path build) {
    Remove-Item -LiteralPath build -Recurse -Force
}
if (Test-Path dist) {
    Remove-Item -LiteralPath dist -Recurse -Force
}
if (Test-Path release) {
    Remove-Item -LiteralPath release -Recurse -Force
}

python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name SoulmaskTrainer `
    main.py

New-Item -ItemType Directory -Force release | Out-Null
Compress-Archive -Path dist\SoulmaskTrainer.exe -DestinationPath release\SoulmaskTrainer-windows.zip -Force

if (Test-Path SoulmaskTrainer.spec) {
    Remove-Item -LiteralPath SoulmaskTrainer.spec -Force
}

Write-Host "Build complete:"
Write-Host "  EXE: $repoRoot\\dist\\SoulmaskTrainer.exe"
Write-Host "  ZIP: $repoRoot\\release\\SoulmaskTrainer-windows.zip"
