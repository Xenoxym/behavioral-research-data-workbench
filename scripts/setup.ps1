$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw 'Install uv or use the Python venv instructions in README.md.'
}
uv sync --frozen
if ($LASTEXITCODE -ne 0) { throw 'Dependency setup failed.' }
& (Join-Path $PSScriptRoot 'setup_research_r.ps1')
uv run research-workbench research
if ($LASTEXITCODE -ne 0) { throw 'Real-data research pipeline failed; inspect the error above.' }
Write-Output 'Ready. Run start_workbench.cmd to open the local application.'
