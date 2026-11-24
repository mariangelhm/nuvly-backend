$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-Not (Test-Path -LiteralPath $pythonPath)) {
  Write-Host "No existe el Python de .venv. Sigue los pasos de instalacion del README.md."
  exit 1
}
& $pythonPath -m uvicorn app.main:app --reload
exit $LASTEXITCODE
