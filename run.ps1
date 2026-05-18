$ErrorActionPreference = "Stop"
if (-Not (Test-Path ".venv")) {
  Write-Host "No existe .venv. Crea el entorno con: python -m venv .venv"
  exit 1
}
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload
