param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet('start', 'stop', 'status', 'restart')]
    [string]$Action
)

$ErrorActionPreference = 'Stop'
$service = 'voice-api.service'
$wslArgs = @('-d', 'Ubuntu', '-u', 'root', '--', 'systemctl')
$stateFile = Join-Path (Split-Path $PSScriptRoot -Parent) '.local-service.pid'
$keepAlive = $null
if (Test-Path -LiteralPath $stateFile) {
    $savedPid = (Get-Content -LiteralPath $stateFile -Raw).Trim()
    if ($savedPid -match '^\d+$') {
        $candidate = Get-CimInstance Win32_Process -Filter "ProcessId = $savedPid"
        if ($candidate -and $candidate.Name -eq 'wsl.exe' -and
            $candidate.CommandLine -match '-d Ubuntu --exec sleep infinity') {
            $keepAlive = $candidate
        }
    }
}

if ($Action -eq 'status') {
    & wsl @wslArgs is-active $service
    $activeCode = $LASTEXITCODE
    & wsl @wslArgs show $service '--property=ActiveState,SubState,MainPID' '--no-pager'
    if ($LASTEXITCODE -ne 0) {
        throw "Could not query $service in WSL Ubuntu (exit code $LASTEXITCODE)."
    }
    if ($activeCode -ne 0 -and $activeCode -ne 3) {
        throw "Could not determine whether $service is active (exit code $activeCode)."
    }
    return
}

if (($Action -eq 'start' -or $Action -eq 'restart') -and -not $keepAlive) {
    # systemd services alone do not prevent WSL from shutting down when idle.
    $keepAlive = Start-Process -FilePath 'wsl.exe' -ArgumentList '-d Ubuntu --exec sleep infinity' -WindowStyle Hidden -PassThru
    Set-Content -LiteralPath $stateFile -Value $keepAlive.Id -Encoding ascii
}

& wsl @wslArgs $Action $service
if ($LASTEXITCODE -ne 0) {
    throw "Could not $Action $service in WSL Ubuntu (exit code $LASTEXITCODE)."
}

if ($Action -eq 'stop') {
    if ($keepAlive) {
        Stop-Process -Id $keepAlive.ProcessId -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $stateFile -ErrorAction SilentlyContinue
}

Write-Host "$service $Action completed."
if ($Action -eq 'start' -or $Action -eq 'restart') {
    Write-Host 'Local API: http://127.0.0.1:8000'
    Write-Host 'The first model load may take some time.'
}
