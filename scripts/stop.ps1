$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
foreach ($service in @('collector', 'bot', 'api', 'web', 'public', 'tunnel')) {
    $pidFile = Join-Path $projectRoot ("run\$service.pid")
    if (-not (Test-Path -LiteralPath $pidFile)) { continue }
    $processId = 0
    if (-not [int]::TryParse((Get-Content -LiteralPath $pidFile -Raw).Trim(), [ref]$processId)) { continue }
    $processInfo = $null
    try { $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction Stop } catch { }
    $liveProcess = Get-Process -Id $processId -ErrorAction SilentlyContinue
    $verified = $liveProcess -and ($liveProcess.Path -like ($projectRoot + '\.venv\*'))
    if ($processInfo -and ($processInfo.CommandLine -like ('*' + $projectRoot + '*') -or $processInfo.ExecutablePath -like ($projectRoot + '\.venv\*'))) { $verified = $true }
    $identityPath = Join-Path $projectRoot ("run\$service.identity.json")
    if ($service -eq 'tunnel' -and $liveProcess -and (Test-Path -LiteralPath $identityPath)) {
        $identity = Get-Content -LiteralPath $identityPath -Raw | ConvertFrom-Json
        $verified = $identity.id -eq $processId -and $liveProcess.ProcessName -eq 'cloudflared' -and $liveProcess.Path -eq $identity.path -and $liveProcess.StartTime.ToUniversalTime().ToString('o') -eq $identity.started
    }
    if ($service -eq 'collector') {
        $verified = $false
        if ($liveProcess -and (Test-Path -LiteralPath $identityPath)) {
            try {
                $identity = Get-Content -LiteralPath $identityPath -Raw | ConvertFrom-Json
                $verified = $identity.id -eq $processId -and $identity.service -eq 'collector' -and $liveProcess.Path -eq $identity.path -and $liveProcess.Path -like ($projectRoot + '\.venv\*') -and $liveProcess.StartTime.ToUniversalTime().ToString('o') -eq $identity.started
            } catch { $verified = $false }
        } elseif ($processInfo -and $processInfo.CommandLine -match '(?:^|\s)app\.daily_worker(?:\s|$)') {
            $verified = $processInfo.ExecutablePath -like ($projectRoot + '\.venv\*')
        }
    }
    if ($verified) {
        # Windows venv Python creates a child interpreter; stop the verified tree.
        & taskkill.exe /PID $processId /T /F 2>$null | Out-Null
        Write-Host "$service to‘xtatildi."
    }
    Remove-Item -LiteralPath $pidFile -ErrorAction SilentlyContinue
    if ($service -eq 'collector' -and (Test-Path -LiteralPath $identityPath)) { Remove-Item -LiteralPath $identityPath -ErrorAction SilentlyContinue }
}
