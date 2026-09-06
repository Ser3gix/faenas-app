$ErrorActionPreference = "Continue"

$url = "https://faenas-app.onrender.com"

Write-Host "Arrancando Faenas desde Render..."
Write-Host $url

$ok = $false
for ($i = 0; $i -lt 24; $i++) {
    try {
        $ready = Invoke-WebRequest -Uri $url -UseBasicParsing -Method Get -TimeoutSec 20
        if ($ready.StatusCode -eq 200) {
            $ok = $true
            break
        }
    } catch {
        Write-Host "Esperando a que Render despierte..."
    }
    Start-Sleep -Seconds 5
}

try {
    Start-Process $url
} catch {
    Write-Host "Abre el navegador en $url"
}

if (-not $ok) {
    Write-Host "Si la pagina tarda, recarga en un minuto. Render a veces esta dormido."
}
