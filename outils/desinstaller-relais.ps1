# Désinstalle le relais montre : arrêt, raccourci de démarrage et fichiers supprimés.
# Les séances retirées de la montre (dossier « retires ») sont conservées.
$ErrorActionPreference = 'Stop'
$Base = Join-Path $env:APPDATA 'MonPlan'
$Shortcut = Join-Path ([Environment]::GetFolderPath('Startup')) 'Relais montre MonPlan.lnk'

Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" |
    Where-Object { $_.CommandLine -like '*montre-relais.ps1*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
if (Test-Path $Shortcut) { Remove-Item $Shortcut -Force }
foreach ($name in 'montre-relais.ps1', 'relais.json', 'relais.log') {
    $p = Join-Path $Base $name
    if (Test-Path $p) { Remove-Item $p -Force }
}
Write-Host 'Relais désinstallé.' -ForegroundColor Green
Write-Host "Séances retirées de la montre conservées dans : $Base\retires"
