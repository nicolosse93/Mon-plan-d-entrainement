# Installe le relais montre : copie dans %APPDATA%\MonPlan, jeton secret, démarrage automatique avec Windows.
# À lancer une fois via installer-relais.cmd (double-clic). Relançable : garde le jeton existant.
param([string]$Site)

$ErrorActionPreference = 'Stop'
$Base = Join-Path $env:APPDATA 'MonPlan'
$Script = Join-Path $Base 'montre-relais.ps1'
$Config = Join-Path $Base 'relais.json'
$Shortcut = Join-Path ([Environment]::GetFolderPath('Startup')) 'Relais montre MonPlan.lnk'
$Port = 47812

New-Item -ItemType Directory -Force -Path $Base | Out-Null
Copy-Item -Path (Join-Path $PSScriptRoot 'montre-relais.ps1') -Destination $Script -Force

# Jeton : conservé s'il existe déjà (l'app n'a pas à être reconfigurée), sinon 32 octets aléatoires
$old = $null
if (Test-Path $Config) { $old = Get-Content -Raw -Encoding UTF8 $Config | ConvertFrom-Json }
$token = if ($old -and $old.token) { $old.token } else {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    -join ($bytes | ForEach-Object { $_.ToString('x2') })
}

# Adresse du site (seule origine en ligne autorisée à parler au relais ; localhost l'est toujours)
if (-not $Site) {
    $default = if ($old -and $old.origins) { @($old.origins)[0] } else { '' }
    $Site = Read-Host "Adresse de ton site (ex. https://monsite.github.io)$(if ($default) { " [Entrée = $default]" } else { ', ou Entrée si tu l''utilises seulement en local' })"
    if (-not $Site) { $Site = $default }
}
$origins = @()
if ($Site) {
    $uri = [Uri]$Site.Trim()
    $origins += "$($uri.Scheme)://$($uri.Authority)"
}
[pscustomobject]@{ token = $token; origins = $origins; port = $Port } | ConvertTo-Json | Set-Content -Path $Config -Encoding UTF8

# Arrête une ancienne instance, crée le raccourci de démarrage, lance le relais
Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" |
    Where-Object { $_.CommandLine -like '*montre-relais.ps1*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
$arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Script`""
$wsh = New-Object -ComObject WScript.Shell
$lnk = $wsh.CreateShortcut($Shortcut)
$lnk.TargetPath = (Get-Command powershell.exe).Source
$lnk.Arguments = $arguments
$lnk.WindowStyle = 7
$lnk.Description = 'Relais entre la montre Garmin et Mon Plan Sportif'
$lnk.Save()
Start-Process -FilePath powershell.exe -ArgumentList $arguments -WindowStyle Hidden

Start-Sleep -Seconds 2
try {
    $status = Invoke-RestMethod -Uri "http://localhost:$Port/status" -Headers @{ 'X-Relais-Jeton' = $token }
    Write-Host "Relais démarré." -ForegroundColor Green
    if ($status.watch) { Write-Host "Montre détectée : $($status.name)" } else { Write-Host 'Montre non branchée pour l''instant (normal).' }
} catch {
    Write-Host "Le relais ne répond pas encore. Détails dans $Base\relais.log" -ForegroundColor Yellow
}

Set-Clipboard -Value $token
Write-Host ''
Write-Host 'Jeton (déjà copié dans le presse-papiers) : colle-le dans l''app : bouton « Montre », puis « Réglages du relais ».' -ForegroundColor Cyan
Write-Host $token
Write-Host ''
Write-Host 'Le relais démarrera tout seul à chaque ouverture de session Windows.'
