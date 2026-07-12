$ErrorActionPreference = "Stop"

$projectPath = "C:\Users\Ser3gix\Desktop\faenas-app"
$serverFile = Join-Path $projectPath "server2.py"
$url = "http://127.0.0.1:5000"
$port = 5000
$pythonExe = Join-Path $projectPath ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    $pythonExe = (Get-Command python.exe -ErrorAction Stop).Source
}

try {
    $existing = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($existing) {
        $pids = $existing | Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($procId in $pids) {
            try { Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue } catch {}
        }
        Start-Sleep -Milliseconds 300
    }
} catch {
    # If TCP inspection fails, keep going and let the launch attempt decide.
}

 $serverProcess = Start-Process -FilePath $pythonExe -ArgumentList @($serverFile) -WorkingDirectory $projectPath -WindowStyle Hidden -PassThru

if (-not $serverProcess) {
    throw "No se pudo iniciar server2.py"
}

$maxChecks = 40
for ($i = 0; $i -lt $maxChecks; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        $ready = Invoke-WebRequest -Uri $url -UseBasicParsing -Method Get -TimeoutSec 2
        if ($ready.StatusCode -eq 200) { break }
    } catch {
        # Wait until the server is ready.
    }
}

Start-Process $url

Wait-Process -Id $serverProcess.Id
