param([int]$Port = 8766)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$runtimeTemp = Join-Path $PSScriptRoot 'data\tmp'
New-Item -ItemType Directory -Force -Path $runtimeTemp | Out-Null
$env:TEMP = $runtimeTemp
$env:TMP = $runtimeTemp
$localPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$workspacePython = Join-Path $PSScriptRoot '..\..\work\runtime\venv\Scripts\python.exe'
if (Test-Path -LiteralPath $localPython) {
    $runtimePython = $localPython
} elseif (Test-Path -LiteralPath $workspacePython) {
    $runtimePython = $workspacePython
} else {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create Python environment.' }
    $runtimePython = $localPython
    & $runtimePython -m pip install --no-cache-dir -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check network and pip configuration.' }
}
& $runtimePython -c 'import langgraph'
if ($LASTEXITCODE -ne 0) {
    & $runtimePython -m pip install --no-cache-dir -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
Write-Host "Open http://127.0.0.1:$Port in your browser."
try {
    $runningService = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/status" -TimeoutSec 2
    if ($runningService.engine -eq 'LangGraph' -and $runningService.version -eq '0.1.0') {
        Write-Host 'Issue Locator is already running on this port.'
        exit 0
    }
} catch {
    # A closed port is expected on the first launch.
}
& $runtimePython -m issue_locator.server --port $Port
