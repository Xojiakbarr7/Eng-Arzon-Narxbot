param([switch]$Postgres)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
New-Item -ItemType Directory -Force -Path backups | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
if ($Postgres) {
    $target = Join-Path $projectRoot ("backups\postgres-$stamp.sql")
    $dump = & docker compose exec -T db pg_dump -U eng_arzon eng_arzon
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL backup bajarilmadi.' }
    $dump | Set-Content -LiteralPath $target -Encoding utf8
} else {
    $target = Join-Path $projectRoot ("backups\catalog-$stamp.db")
    $pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Avval start.ps1 bilan muhitni tayyorlang.' }
    $source = Join-Path $projectRoot 'backend\data\catalog.db'
    if (-not (Test-Path -LiteralPath $source)) { throw 'SQLite bazasi topilmadi.' }
    & $pythonPath -c 'import sqlite3,sys; src=sqlite3.connect(sys.argv[1]); dst=sqlite3.connect(sys.argv[2]); src.backup(dst); dst.close(); src.close()' $source $target
    if ($LASTEXITCODE -ne 0) { throw 'SQLite backup bajarilmadi.' }
}
Write-Host "Backup tayyor: $target"
