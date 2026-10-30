param(
    [string]$Python = "",
    [switch]$WithBot,
    [switch]$WithCollector,
    [switch]$SkipInstall
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

function New-LocalSecret {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return ([BitConverter]::ToString($bytes)).Replace('-', '').ToLowerInvariant()
}
function Test-LocalPort {
    param([int]$PortNumber)
    $taskClient = [System.Net.Sockets.TcpClient]::new()
    try {
        $taskConnect = $taskClient.ConnectAsync([System.Net.IPAddress]::Loopback, $PortNumber)
        if (-not $taskConnect.Wait(3000)) {
            throw [System.TimeoutException]::new("Port $PortNumber holatini tekshirish vaqti tugadi.")
        }
        return $taskClient.Connected
    } catch {
        $taskBaseError = $_.Exception.GetBaseException()
        if ($taskBaseError -is [System.Net.Sockets.SocketException] -and $taskBaseError.SocketErrorCode -eq [System.Net.Sockets.SocketError]::ConnectionRefused) { return $false }
        if ($taskBaseError -is [System.TimeoutException]) { throw "Port $PortNumber holatini tekshirish vaqti tugadi." }
        throw "Port $PortNumber holatini tekshirib bo‘lmadi."
    } finally { $taskClient.Dispose() }
}
function Read-LocalEnvValue {
    param([string]$Text, [string]$Name)
    $processValue = [Environment]::GetEnvironmentVariable($Name, 'Process')
    if ($null -ne $processValue) { return $processValue.Trim() }
    $match = [regex]::Match($Text, ('(?m)^\s*' + [regex]::Escape($Name) + '\s*=\s*(.*?)\s*$'))
    if (-not $match.Success) { return '' }
    $value = $match.Groups[1].Value.Trim()
    if ($value.Length -ge 2 -and (($value.StartsWith("'") -and $value.EndsWith("'")) -or ($value.StartsWith('"') -and $value.EndsWith('"')))) {
        return $value.Substring(1, $value.Length - 2)
    }
    return ($value -split '\s+#', 2)[0].Trim()
}
function Assert-CollectorConfiguration {
    param([string]$Text)
    $enabled = Read-LocalEnvValue $Text 'COLLECTION_ENABLED'
    if ($enabled.ToLowerInvariant() -notin @('true', '1', 'yes')) {
        throw 'Kollektor uchun .env faylida COLLECTION_ENABLED=true sozlang. Kanalga yozish DAILY_POST_ENABLED orqali alohida boshqariladi.'
    }
    $posts = Read-LocalEnvValue $Text 'DAILY_POST_ENABLED'
    if ($posts.ToLowerInvariant() -in @('true', '1', 'yes')) {
        $channel = Read-LocalEnvValue $Text 'DAILY_CHANNEL_ID'
        $token = Read-LocalEnvValue $Text 'BOT_TOKEN'
        if (-not $token -or $channel -notmatch '^(?:@[A-Za-z][A-Za-z0-9_]{4,31}|-100\d{5,})$') {
            throw "Kanalga yuborish uchun .env faylida BOT_TOKEN va DAILY_CHANNEL_ID sozlang; bot kanalda post yozish huquqiga ega administrator bo‘lsin."
        }
    }
}
# Check before installing, building, launching, or replacing existing PID files.
foreach ($portNumber in @(8000, 5173)) {
    if (Test-LocalPort $portNumber) {
        throw "$portNumber port band. Ishlayotgan xizmatlar o‘zgartirilmadi; avval ularni to‘xtating."
    }
}
if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
}
$envText = Get-Content -LiteralPath '.env' -Raw
if ($WithCollector) {
    Assert-CollectorConfiguration $envText
    $collectorPidPath = Join-Path $projectRoot 'run\collector.pid'
    if (Test-Path -LiteralPath $collectorPidPath) {
        $collectorRecordedId = 0
        if ([int]::TryParse((Get-Content -LiteralPath $collectorPidPath -Raw).Trim(), [ref]$collectorRecordedId)) {
            $existingCollector = Get-Process -Id $collectorRecordedId -ErrorAction SilentlyContinue
            if ($existingCollector -and $existingCollector.Path -like ($projectRoot + '\.venv\*')) {
                throw "Kollektor uchun saqlangan loyiha jarayoni hali ishlayapti. Avval scripts\stop.ps1 orqali to‘xtating."
            }
        }
    }
}
foreach ($name in @('ADMIN_TOKEN', 'BOT_INTERNAL_TOKEN', 'POSTGRES_PASSWORD')) {
    if ($envText -match "(?m)^$name=[^\S\r\n]*\r?$") {
        $envText = [regex]::Replace($envText, "(?m)^$name=[^\S\r\n]*\r?$", ($name + '=' + (New-LocalSecret)))
    }
}
[System.IO.File]::WriteAllText((Join-Path $projectRoot '.env'), $envText, (New-Object System.Text.UTF8Encoding $false))
if (-not $Python) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) { $Python = $pythonCommand.Source }
    else {
        $bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
        if (Test-Path -LiteralPath $bundledPython) { $Python = $bundledPython }
        else { throw 'Python 3.11+ topilmadi. -Python C:\path\python.exe argumentini bering.' }
    }
}
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    & $Python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual muhit yaratilmadi.' }
}
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not $SkipInstall) {
    & $venvPython -m pip install -r backend/requirements.txt -r bot/requirements.txt -c requirements-lock.txt
    if ($LASTEXITCODE -ne 0) { throw "Python kutubxonalari o‘rnatilmadi." }
    $pnpmCommand = Get-Command pnpm.cmd -ErrorAction SilentlyContinue
    $pnpmPath = if ($pnpmCommand) { $pnpmCommand.Source } else { Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd' }
    $npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not (Test-Path -LiteralPath $pnpmPath) -and -not $npmCommand) { throw 'Node.js 22+ hamda npm yoki pnpm kerak.' }
    Push-Location -LiteralPath frontend
    try {
        if (Test-Path -LiteralPath $pnpmPath) { & $pnpmPath install --frozen-lockfile --ignore-scripts }
        else { & $npmCommand.Source install --no-audit --no-fund }
        if ($LASTEXITCODE -ne 0) { throw "Frontend kutubxonalari o‘rnatilmadi." }
    } finally { Pop-Location }
}
$nodeCommand = Get-Command node -ErrorAction SilentlyContinue
if (-not $nodeCommand) { throw 'Node.js topilmadi.' }
if ($WithBot -and $envText -notmatch '(?m)^BOT_TOKEN=\S+') {
    throw 'Telegram bot uchun avval .env faylida BOT_TOKEN sozlang.'
}
New-Item -ItemType Directory -Force -Path run | Out-Null
$frontendDir = Join-Path $projectRoot 'frontend'
$vitePath = Join-Path $frontendDir 'node_modules\vite\bin\vite.js'
$tscPath = Join-Path $frontendDir 'node_modules\typescript\bin\tsc'
if (-not (Test-Path -LiteralPath $vitePath) -or -not (Test-Path -LiteralPath $tscPath)) {
    throw "Frontend kutubxonalari yo‘q. -SkipInstall parametrini olib qayta ishga tushiring."
}
Push-Location -LiteralPath $frontendDir
try {
    & $nodeCommand.Source $tscPath -b
    if ($LASTEXITCODE -ne 0) { throw 'TypeScript tekshiruvi bajarilmadi.' }
    & $nodeCommand.Source $vitePath build --configLoader native
    if ($LASTEXITCODE -ne 0) { throw "Mini App yig‘ilmadi." }
} finally { Pop-Location }
$backendDir = Join-Path $projectRoot 'backend'
if ($WithCollector) {
    Push-Location -LiteralPath $backendDir
    try {
        # Validate with the worker's own dotenv/parser before starting any service.
        @'
from dotenv import load_dotenv
load_dotenv("../.env")
from app.daily_worker import DailySettings
from pathlib import Path
import json
settings = DailySettings.from_env()
assert settings.enabled, "COLLECTION_ENABLED=true kerak"
assert Path(settings.config_path).is_file(), "COLLECTION_CONFIG fayli topilmadi"
json.loads(Path(settings.config_path).read_text(encoding="utf-8-sig"))
'@ | & $venvPython -
        if ($LASTEXITCODE -ne 0) { throw 'Kollektor sozlamalari yaroqsiz. .env va backend\collection-sources.json fayllarini tekshiring.' }
    } finally { Pop-Location }
}
$apiArguments = @('-m', 'uvicorn', 'app.main:app', '--app-dir', ('"' + $backendDir + '"'), '--host', '127.0.0.1', '--port', '8000')
$startedServices = [System.Collections.Generic.List[object]]::new()
function Assert-NewServicesAlive {
    foreach ($taskService in $startedServices) {
        $taskService.Process.Refresh()
        if ($taskService.Process.HasExited) {
            throw "$($taskService.Name) jarayoni to‘xtadi. $($taskService.ErrorLog) faylini tekshiring."
        }
        if (Test-Path -LiteralPath $taskService.ErrorLog) {
            $taskStartupLog = Get-Content -LiteralPath $taskService.ErrorLog -Raw -ErrorAction SilentlyContinue
            if ($taskStartupLog -match '(?im)(?:^|\s)ERROR(?:\s|:)|^Traceback\b|Telegram(?:Unauthorized|Conflict)Error|\[Errno 10048\]|Port \d+ is already in use') {
                throw "$($taskService.Name) ishga tushish xatosi. $($taskService.ErrorLog) faylini tekshiring."
            }
        }
    }
}
try {
    $apiErrorLog = Join-Path $projectRoot 'run\api.err.log'
    $apiProcess = Start-Process -FilePath $venvPython -ArgumentList $apiArguments -WorkingDirectory $backendDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot 'run\api.out.log') -RedirectStandardError $apiErrorLog
    $startedServices.Add([pscustomobject]@{Name='api'; Process=$apiProcess; ErrorLog=$apiErrorLog})
    $webErrorLog = Join-Path $projectRoot 'run\web.err.log'
    $webProcess = Start-Process -FilePath $nodeCommand.Source -ArgumentList @(('"' + $vitePath + '"'), 'preview', '--configLoader', 'native', '--host', '127.0.0.1', '--port', '5173', '--strictPort') -WorkingDirectory $frontendDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot 'run\web.out.log') -RedirectStandardError $webErrorLog
    $startedServices.Add([pscustomobject]@{Name='web'; Process=$webProcess; ErrorLog=$webErrorLog})
    if ($WithBot) {
        $botErrorLog = Join-Path $projectRoot 'run\bot.err.log'
        $botProcess = Start-Process -FilePath $venvPython -ArgumentList @('-m', 'bot.main') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot 'run\bot.out.log') -RedirectStandardError $botErrorLog
        $startedServices.Add([pscustomobject]@{Name='bot'; Process=$botProcess; ErrorLog=$botErrorLog})
    }
    Start-Sleep -Milliseconds 500
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Assert-NewServicesAlive
        try { Invoke-RestMethod 'http://127.0.0.1:8000/api/health' -TimeoutSec 2 | Out-Null; $ready = $true; break }
        catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $ready) { throw 'API ishga tushmadi. run\api.err.log faylini tekshiring.' }
    $webReady = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Assert-NewServicesAlive
        try { Invoke-WebRequest 'http://127.0.0.1:5173' -UseBasicParsing -TimeoutSec 2 | Out-Null; $webReady = $true; break }
        catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $webReady) { throw 'Mini App ishga tushmadi. run\web.err.log faylini tekshiring.' }
    if ($WithBot) {
        $botReady = $false
        for ($attempt = 0; $attempt -lt 60; $attempt++) {
            Assert-NewServicesAlive
            if ((Get-Content -LiteralPath $botErrorLog -Raw -ErrorAction SilentlyContinue) -match 'Run polling for bot') { $botReady = $true; break }
            Start-Sleep -Milliseconds 500
        }
        if (-not $botReady) { throw 'Bot Telegramga ulanmagan. run\bot.err.log faylini tekshiring.' }
    }
    if ($WithCollector) {
        $collectorErrorLog = Join-Path $projectRoot 'run\collector.err.log'
        $collectorProcess = Start-Process -FilePath $venvPython -ArgumentList @('-u', '-m', 'app.daily_worker') -WorkingDirectory $backendDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot 'run\collector.out.log') -RedirectStandardError $collectorErrorLog
        $startedServices.Add([pscustomobject]@{Name='collector'; Process=$collectorProcess; ErrorLog=$collectorErrorLog})
        $collectorReady = $false
        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            Assert-NewServicesAlive
            if ((Get-Content -LiteralPath $collectorErrorLog -Raw -ErrorAction SilentlyContinue) -match 'Daily worker ready') { $collectorReady = $true; break }
            Start-Sleep -Milliseconds 500
        }
        if (-not $collectorReady) { throw 'Kollektor tayyorlikni tasdiqlamadi. run\collector.err.log faylini tekshiring.' }
    }
    Start-Sleep -Milliseconds 500
    Assert-NewServicesAlive
    # Publish PIDs only after the processes from this invocation are ready.
    foreach ($taskService in $startedServices) {
        $taskService.Process.Id | Set-Content -LiteralPath (Join-Path $projectRoot ("run\$($taskService.Name).pid"))
        if ($taskService.Name -eq 'collector') {
            $taskService.Process.Refresh()
            @{ id=$taskService.Process.Id; service='collector'; path=$taskService.Process.Path; started=$taskService.Process.StartTime.ToUniversalTime().ToString('o') } |
                ConvertTo-Json | Set-Content -LiteralPath (Join-Path $projectRoot 'run\collector.identity.json')
        }
    }
} catch {
    foreach ($taskService in $startedServices) {
        $taskService.Process.Refresh()
        if (-not $taskService.Process.HasExited) {
            # These are fresh processes from this invocation, including venv children.
            try { & taskkill.exe /PID $taskService.Process.Id /T /F 2>$null | Out-Null } catch { }
        }
        $taskPidFile = Join-Path $projectRoot ("run\$($taskService.Name).pid")
        if (Test-Path -LiteralPath $taskPidFile) {
            $taskRecordedId = 0
            if ([int]::TryParse((Get-Content -LiteralPath $taskPidFile -Raw).Trim(), [ref]$taskRecordedId) -and $taskRecordedId -eq $taskService.Process.Id) {
                Remove-Item -LiteralPath $taskPidFile -ErrorAction SilentlyContinue
            }
        }
        if ($taskService.Name -eq 'collector') {
            $taskIdentityPath = Join-Path $projectRoot 'run\collector.identity.json'
            if (Test-Path -LiteralPath $taskIdentityPath) {
                try {
                    $taskIdentity = Get-Content -LiteralPath $taskIdentityPath -Raw | ConvertFrom-Json
                    if ($taskIdentity.id -eq $taskService.Process.Id) { Remove-Item -LiteralPath $taskIdentityPath -ErrorAction SilentlyContinue }
                } catch { }
            }
        }
    }
    throw
}
Write-Host 'Mini App: http://127.0.0.1:5173'
Write-Host 'API hujjati: http://127.0.0.1:8000/docs'
if ($WithCollector) { Write-Host 'Kunlik kollektor ishga tushdi. Jadval va kanal: .env; loglar: run\collector.*.log' }
Write-Host "Maxfiy tokenlar .env faylida. To‘xtatish: .\scripts\stop.ps1"
