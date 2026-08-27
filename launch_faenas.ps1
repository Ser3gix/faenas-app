$ErrorActionPreference = "Stop"

$projectPath = "C:\Users\Ser3gix\Desktop\faenas-app"
$serverFile = Join-Path $projectPath "server2.py"
$url = "http://127.0.0.1:5000"
$port = 5000
$pythonExe = Join-Path $projectPath ".venv\Scripts\python.exe"

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

    if (-not $candidates) {
        try {
            $net = & netstat -ano -p tcp | Select-String ":$port\s+.*LISTENING" -SimpleMatch
            foreach ($line in $net) {
                $parts = $line -split '\s+'
                if ($parts.Count -ge 5) {
                    $pid = $parts[-1]
                    if ($pid -match '^\d+$') { $candidates += [int]$pid }
                }
            }
        } catch {}
    }

    $seen = @{}
    foreach ($pid in $candidates | Sort-Object -Unique) {
        if (-not $pid) { continue }
        if ($seen.ContainsKey([string]$pid)) { continue }
        $seen[[string]$pid] = $true

        try {
            $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
            if ($proc) {
                Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
                Write-Host "Detenido proceso antiguo en puerto $port (PID $pid)"
            }
        } catch {}
    }
}

if (-not (Test-Path $pythonExe)) {
    $pythonExe = (Get-Command python.exe -ErrorAction Stop).Source
}

Stop-StaleFaenasProcesses
Start-Sleep -Milliseconds 500

$serverProcess = Start-Process -FilePath $pythonExe -ArgumentList @($serverFile) -WorkingDirectory $projectPath -WindowStyle Hidden -PassThru

if (-not $serverProcess) {
    throw "No se pudo iniciar server2.py"
}

$maxChecks = 60
for ($i = 0; $i -lt $maxChecks; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        $ready = Invoke-WebRequest -Uri $url -UseBasicParsing -Method Get -TimeoutSec 2
        if ($ready.StatusCode -eq 200) { break }
    } catch {}
}

try {
    Start-Process $url
} catch {}

Wait-Process -Id $serverProcess.Id
