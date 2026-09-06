param(
    [switch]$SoloActualizar
)

$ErrorActionPreference = "Stop"

$projectPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$serverFile = Join-Path $projectPath "server2.py"
$urlLocal = "http://127.0.0.1:5000"
$urlNube = "https://faenas-app.onrender.com"
$zipUrl = "https://github.com/Ser3gix/faenas-app/archive/refs/heads/main.zip"
$port = 5000
$pythonExe = Join-Path $projectPath ".venv\Scripts\python.exe"

function Update-FaenasApp {
    Write-Host "Actualizando Faenas..."
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $tmp = Join-Path $env:TEMP ("faenas-update-" + [guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Path $tmp | Out-Null
        $zip = Join-Path $tmp "faenas.zip"
        Write-Host "Descargando la version nueva..."
        Invoke-WebRequest -Uri $zipUrl -OutFile $zip -UseBasicParsing
        Expand-Archive -Path $zip -DestinationPath $tmp -Force
        $src = Get-ChildItem -Path $tmp -Directory | Select-Object -First 1
        if (-not $src) { throw "No se pudo descomprimir" }
        $xd = @("datos", "faenas-datos", ".git", ".venv", "__pycache__", "descargas_raul")
        $copyArgs = @($src.FullName, $projectPath, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/nc", "/ns", "/np")
        foreach ($d in $xd) { $copyArgs += @("/XD", $d) }
        $copyArgs += @("/XF", ".env")
        & robocopy @copyArgs | Out-Null
        Write-Host "App actualizada."
    } catch {
        Write-Host "No se pudo actualizar ahora. Sigo con la version que hay en la carpeta."
        Write-Host $_.Exception.Message
    } finally {
        $ErrorActionPreference = $prev
    }
}

Write-Host "Faenas PC"
Write-Host "  Datos y faenas: $urlNube"
Write-Host "  Este ordenador lee los PDF que se suban en la web"
Write-Host ""

Update-FaenasApp

if ($SoloActualizar) {
    Write-Host ""
    Write-Host "Listo. Ya puedes cerrar esta ventana y pulsar Arrancar_Faenas.bat"
    exit 0
}

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
