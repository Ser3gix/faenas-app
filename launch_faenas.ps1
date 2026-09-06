$ErrorActionPreference = "Stop"

$projectPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$serverFile = Join-Path $projectPath "server2.py"
$urlLocal = "http://127.0.0.1:5000"
$urlNube = "https://faenas-app.onrender.com"
$port = 5000
$pythonExe = Join-Path $projectPath ".venv\Scripts\python.exe"

Write-Host "Faenas PC"
Write-Host "  Datos y faenas: $urlNube"
Write-Host "  Lectura de PDF: este ordenador"
Write-Host ""

function Stop-StaleFaenasProcesses {
    $candidates = @()
    try {
        $candidates += Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object {
                $_.Name -match 'python(\.exe|w\.exe)?' -and (
                    ($_.CommandLine -match 'server2\.py' -or $_.CommandLine -match 'server\.py' -or $_.CommandLine -match 'faenas-app')
                )
            } |
            Select-Object -ExpandProperty ProcessId -Unique
    } catch {}

    try {
        $existing = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if ($existing) {
            $candidates += $existing | Select-Object -ExpandProperty OwningProcess -Unique
        }
    } catch {}

    $seen = @{}
    foreach ($procId in $candidates | Sort-Object -Unique) {
        if (-not $procId) { continue }
        if ($seen.ContainsKey([string]$procId)) { continue }
        $seen[[string]$procId] = $true
        try {
            $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
            if ($proc) {
                Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
                Write-Host "Cerrada una Faenas anterior (PID $procId)"
            }
        } catch {}
    }
}

if (-not (Test-Path $pythonExe)) {
    $pythonExe = (Get-Command python.exe -ErrorAction Stop).Source
}

if (-not (Test-Path $serverFile)) {
    throw "No encuentro server2.py en $projectPath"
}

Write-Host "Despertando la nube..."
Start-Job -ScriptBlock {
    param($u)
    try { Invoke-WebRequest -Uri $u -UseBasicParsing -Method Get -TimeoutSec 90 | Out-Null } catch {}
} -ArgumentList $urlNube | Out-Null

Stop-StaleFaenasProcesses
Start-Sleep -Milliseconds 400

$serverProcess = Start-Process -FilePath $pythonExe -ArgumentList @($serverFile) -WorkingDirectory $projectPath -WindowStyle Hidden -PassThru
if (-not $serverProcess) {
    throw "No se pudo iniciar la app del PC"
}

$maxChecks = 60
$ready = $false
for ($i = 0; $i -lt $maxChecks; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        $ping = Invoke-WebRequest -Uri $urlLocal -UseBasicParsing -Method Get -TimeoutSec 2
        if ($ping.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
}

if (-not $ready) {
    throw "La app del PC no ha arrancado. Mira si Python y Tesseract estan instalados."
}

Write-Host "Listo. Abriendo $urlLocal"
try { Start-Process $urlLocal } catch { Write-Host "Abre el navegador en $urlLocal" }

Wait-Process -Id $serverProcess.Id
