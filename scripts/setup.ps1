$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw 'Install uv or use the Python venv instructions in README.md.'
}
uv sync --frozen
if ($LASTEXITCODE -ne 0) { throw 'Dependency setup failed.' }
uv run research-workbench demo
if ($LASTEXITCODE -ne 0) { throw 'Demo initialization failed. Existing data was preserved.' }
Write-Output 'Ready. Run start_workbench.cmd to open the local application.'
