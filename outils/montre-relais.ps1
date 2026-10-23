# Relais local entre la montre Garmin (branchée en USB) et l'app « Mon Plan Sportif ».
# Les navigateurs ne savent pas lire une montre en MTP (sans lettre de lecteur) : ce petit serveur, lancé en
# silence avec Windows par installer-relais.ps1, le fait à leur place via la couche « Appareils » de l'Explorateur.
#
# Routes (toutes protégées par le jeton, en-tête X-Relais-Jeton) :
#   GET  /status                       montre branchée ? nom de l'appareil
#   GET  /activities?days=30           sorties récentes de GARMIN\Activity (nom, taille, date)
#   GET  /activities/<nom>.fit         contenu d'une sortie
#   POST /workouts/<nom>.fit           dépose une séance dans GARMIN\NewFiles (prise en compte au débranchement)
#   POST /cleanup?before=AAAA-MM-JJ    retire les séances de l'app datées d'avant cette date (déplacées, pas effacées)
#
# -DossierTest <chemin> : utilise un dossier normal contenant GARMIN\... à la place de la montre (tests).
param(
    [string]$Config = (Join-Path $env:APPDATA 'MonPlan\relais.json'),
    [string]$DossierTest,
    [string]$Jeton,
    [string[]]$Origines,
    [int]$Port = 47812
)

$ErrorActionPreference = 'Stop'
$Base = if ($DossierTest) { Join-Path $DossierTest '_relais' } else { Join-Path $env:APPDATA 'MonPlan' }
$Temp = Join-Path $env:TEMP 'monplan-relais'
$Retires = Join-Path $Base 'retires'
$LogFile = Join-Path $Base 'relais.log'
New-Item -ItemType Directory -Force -Path $Base, $Temp, $Retires | Out-Null

if (-not $Jeton) {
    $cfg = Get-Content -Raw -Encoding UTF8 $Config | ConvertFrom-Json
    $Jeton = $cfg.token
    $Origines = @($cfg.origins)
    if ($cfg.port) { $Port = [int]$cfg.port }
}
if (-not $Jeton -or $Jeton.Length -lt 32) { throw 'Jeton absent ou trop court : relance installer-relais.ps1' }

function Write-Log([string]$text) {
    try { Add-Content -Path $LogFile -Value ("{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $text) -Encoding UTF8 } catch {}
}

# Origines autorisées : celles de la configuration + l'app lancée en local (tests)
function Test-Origin([string]$origin) {
    if (-not $origin) { return $true } # pas de navigateur (ex. curl) : seul le jeton protège
    if ($Origines -contains $origin) { return $true }
    return $origin -match '^http://(localhost|127\.0\.0\.1)(:\d+)?$'
}

# Nom de fichier simple uniquement : ni chemin, ni « .. »
function Test-FileName([string]$name) {
    return ($name -match '^[\w][\w.-]*\.fit$') -and ($name -notmatch '\.\.')
}

# ---------------------------------------------------------------------------
# Accès à la montre : MTP (Shell.Application), lecteur classique, ou dossier de test
# ---------------------------------------------------------------------------
$Shell = New-Object -ComObject Shell.Application
$CopyFlags = 4 + 16 + 1024 # pas de fenêtre de progression, « oui à tout », pas d'erreur affichée

function Get-ChildFolder($folder, [string]$name) {
    foreach ($item in $folder.Items()) {
        if ($item.IsFolder -and $item.Name -eq $name) { return $item.GetFolder }
    }
    return $null
}

# Nom réel du fichier (avec extension, même si l'Explorateur masque les extensions)
function Get-ItemFileName($item) {
    $name = $null
    try { $name = $item.ExtendedProperty('System.FileName') } catch {}
    if (-not $name) { $name = $item.Name }
    if ($name -notmatch '\.fit$') { $name = "$name.fit" }
    return $name
}

# Racine GARMIN de la montre : @{ Name; Kind = 'shell' | 'path'; Garmin = dossier Shell ou chemin }
function Find-Watch {
    if ($DossierTest) {
        $p = Join-Path $DossierTest 'GARMIN'
        if (Test-Path $p) { return @{ Name = 'Dossier de test'; Kind = 'path'; Garmin = $p } }
        return $null
    }
    foreach ($dev in $Shell.Namespace(17).Items()) { # 17 = « Ce PC »
        if (-not $dev.IsFolder) { continue }
        if ($dev.Path -match '^[A-Za-z]:\\$') {
            # Montre en mode lecteur (ancien modèle) : GARMIN à la racine
            $p = Join-Path $dev.Path 'GARMIN'
            if (Test-Path (Join-Path $p 'Activity')) { return @{ Name = $dev.Name; Kind = 'path'; Garmin = $p } }
            continue
        }
        # Appareil MTP : GARMIN à la racine ou dans un stockage (« Internal Storage », « Primary »…)
        $root = $dev.GetFolder
        if (-not $root) { continue }
        $garmin = Get-ChildFolder $root 'GARMIN'
        if (-not $garmin) {
            foreach ($storage in $root.Items()) {
                if ($storage.IsFolder) {
                    $garmin = Get-ChildFolder $storage.GetFolder 'GARMIN'
                    if ($garmin) { break }
                }
            }
        }
        if ($garmin) { return @{ Name = $dev.Name; Kind = 'shell'; Garmin = $garmin } }
    }
    return $null
}

# Fichiers d'un sous-dossier de GARMIN : @{ Name; Size; Modified; Item (Shell) ou Path }
function Get-WatchFiles($watch, [string]$sub) {
    $files = @()
    if ($watch.Kind -eq 'path') {
        $dir = Join-Path $watch.Garmin $sub
        if (-not (Test-Path $dir)) { return @() }
        foreach ($f in Get-ChildItem -Path $dir -Filter '*.fit' -File) {
            $files += @{ Name = $f.Name; Size = $f.Length; Modified = $f.LastWriteTime; Path = $f.FullName }
        }
        return $files
    }
    $folder = Get-ChildFolder $watch.Garmin $sub
    if (-not $folder) { return @() }
    foreach ($item in $folder.Items()) {
        if ($item.IsFolder) { continue }
        $files += @{ Name = (Get-ItemFileName $item); Size = [long]$item.Size; Modified = $item.ModifyDate; Item = $item }
    }
    return $files
}

# Attend qu'un fichier local existe avec la taille attendue (copie Shell asynchrone)
function Wait-LocalFile([string]$path, [long]$size, [int]$timeoutSec = 30) {
    $limit = (Get-Date).AddSeconds($timeoutSec)
    while ((Get-Date) -lt $limit) {
        if (Test-Path $path) {
            $len = (Get-Item $path).Length
            if ($len -gt 0 -and ($size -le 0 -or $len -ge $size)) { Start-Sleep -Milliseconds 200; return $true }
        }
        Start-Sleep -Milliseconds 200
    }
    return $false
}

function Read-WatchFile($watch, $file) {
    # « return , » : renvoie le tableau d'octets tel quel (sans le dérouler)
    if ($file.Path) { return , [System.IO.File]::ReadAllBytes($file.Path) }
    $local = Join-Path $Temp $file.Name
    if (Test-Path $local) { Remove-Item $local -Force }
    $Shell.Namespace($Temp).CopyHere($file.Item, $CopyFlags)
    if (-not (Wait-LocalFile $local $file.Size)) { throw "Copie de $($file.Name) depuis la montre trop longue" }
    return , [System.IO.File]::ReadAllBytes($local)
}

function Write-WatchWorkout($watch, [string]$name, [byte[]]$bytes) {
    if ($watch.Kind -eq 'path') {
        $dir = Join-Path $watch.Garmin 'NewFiles'
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        [System.IO.File]::WriteAllBytes((Join-Path $dir $name), $bytes)
        return
    }
    $newFiles = Get-ChildFolder $watch.Garmin 'NewFiles'
    if (-not $newFiles) { throw 'Dossier GARMIN\NewFiles introuvable sur la montre' }
    $local = Join-Path $Temp $name
    [System.IO.File]::WriteAllBytes($local, $bytes)
    $newFiles.CopyHere($local, $CopyFlags)
    $limit = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $limit) {
        foreach ($item in $newFiles.Items()) { if ((Get-ItemFileName $item) -eq $name) { return } }
        Start-Sleep -Milliseconds 300
    }
    throw "Écriture de $name sur la montre trop longue"
}

# Déplace (sans effacer) vers %APPDATA%\MonPlan\retires
function Move-WatchFileAway($watch, $file) {
    $target = Join-Path $Retires $file.Name
    if (Test-Path $target) { Remove-Item $target -Force }
    if ($file.Path) { Move-Item -Path $file.Path -Destination $target; return }
    $Shell.Namespace($Retires).MoveHere($file.Item, $CopyFlags)
    if (-not (Wait-LocalFile $target $file.Size)) { throw "Retrait de $($file.Name) trop long" }
}

# ---------------------------------------------------------------------------
# Serveur HTTP local
# ---------------------------------------------------------------------------
function Send-Response($ctx, [int]$code, $body, [string]$type = 'application/json; charset=utf-8') {
    $res = $ctx.Response
    $origin = $ctx.Request.Headers['Origin']
    if ($origin -and (Test-Origin $origin)) {
        $res.AddHeader('Access-Control-Allow-Origin', $origin)
        $res.AddHeader('Vary', 'Origin')
    }
    $res.StatusCode = $code
    $res.ContentType = $type
    # Affectations dans les blocs : un tableau renvoyé par une expression serait « déroulé » par PowerShell
    if ($body -is [byte[]]) { $bytes = $body } else { $bytes = [System.Text.Encoding]::UTF8.GetBytes([string]$body) }
    $res.ContentLength64 = $bytes.Length
    if ($bytes.Length -gt 0) { $res.OutputStream.Write($bytes, 0, $bytes.Length) }
    $res.Close()
}

# JSON ; les listes sont sérialisées élément par élément (ConvertTo-Json de PowerShell 5.1 les emballe sinon)
function ConvertTo-JsonValue($value) {
    if ($value -is [array]) {
        return '[' + ((@($value) | ForEach-Object { ConvertTo-JsonValue $_ }) -join ',') + ']'
    }
    if ($value -is [hashtable]) {
        $pairs = foreach ($key in $value.Keys) { (ConvertTo-Json -InputObject ([string]$key)) + ':' + (ConvertTo-JsonValue $value[$key]) }
        return '{' + (@($pairs) -join ',') + '}'
    }
    return ConvertTo-Json -InputObject $value -Compress
}

function Send-Json($ctx, [int]$code, $value) {
    Send-Response $ctx $code (ConvertTo-JsonValue $value)
}

function Read-Body($req, [long]$max) {
    if ($req.ContentLength64 -gt $max) { throw 'Fichier trop gros' }
    $ms = New-Object System.IO.MemoryStream
    $req.InputStream.CopyTo($ms)
    if ($ms.Length -gt $max) { throw 'Fichier trop gros' }
    return , $ms.ToArray()
}

function Invoke-Route($ctx) {
    $req = $ctx.Request
    $origin = $req.Headers['Origin']
    if (-not (Test-Origin $origin)) { Send-Json $ctx 403 @{ error = 'Origine non autorisée' }; return }

    # Pré-contrôle CORS (+ accès au réseau local depuis un site public)
    if ($req.HttpMethod -eq 'OPTIONS') {
        $res = $ctx.Response
        $res.AddHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        $res.AddHeader('Access-Control-Allow-Headers', 'X-Relais-Jeton, Content-Type')
        $res.AddHeader('Access-Control-Allow-Private-Network', 'true')
        $res.AddHeader('Access-Control-Max-Age', '600')
        Send-Response $ctx 204 ''
        return
    }
    if ($req.Headers['X-Relais-Jeton'] -cne $Jeton) { Send-Json $ctx 401 @{ error = 'Jeton refusé' }; return }

    $path = [Uri]::UnescapeDataString($req.Url.AbsolutePath)
    $watch = Find-Watch

    if ($req.HttpMethod -eq 'GET' -and $path -eq '/status') {
        Send-Json $ctx 200 @{ relay = $true; watch = [bool]$watch; name = $(if ($watch) { $watch.Name } else { $null }) }
        return
    }
    if (-not $watch) { Send-Json $ctx 409 @{ error = 'Montre non détectée' }; return }

    if ($req.HttpMethod -eq 'GET' -and $path -eq '/activities') {
        $days = 30
        if ($req.QueryString['days']) { $days = [Math]::Min(365, [Math]::Max(1, [int]$req.QueryString['days'])) }
        $since = (Get-Date).AddDays(-$days)
        $list = @(Get-WatchFiles $watch 'Activity' | Where-Object { $_.Modified -ge $since } |
            Sort-Object { $_.Modified } | ForEach-Object {
                @{ name = $_.Name; size = $_.Size; modified = ([datetime]$_.Modified).ToString('s') }
            })
        Send-Json $ctx 200 $list
        return
    }
    if ($req.HttpMethod -eq 'GET' -and $path -match '^/activities/([^/]+)$') {
        $name = $Matches[1]
        if (-not (Test-FileName $name)) { Send-Json $ctx 400 @{ error = 'Nom de fichier invalide' }; return }
        $file = Get-WatchFiles $watch 'Activity' | Where-Object { $_.Name -eq $name } | Select-Object -First 1
        if (-not $file) { Send-Json $ctx 404 @{ error = 'Sortie introuvable' }; return }
        Send-Response $ctx 200 (Read-WatchFile $watch $file) 'application/octet-stream'
        return
    }
    if ($req.HttpMethod -eq 'POST' -and $path -match '^/workouts/([^/]+)$') {
        $name = $Matches[1]
        if (-not (Test-FileName $name)) { Send-Json $ctx 400 @{ error = 'Nom de fichier invalide' }; return }
        $bytes = Read-Body $req 1MB
        if ($bytes.Length -lt 14 -or [System.Text.Encoding]::ASCII.GetString($bytes, 8, 4) -ne '.FIT') {
            Send-Json $ctx 400 @{ error = "Ce n'est pas un fichier .FIT" }; return
        }
        Write-WatchWorkout $watch $name $bytes
        Write-Log "Séance envoyée : $name"
        Send-Json $ctx 200 @{ ok = $true }
        return
    }
    if ($req.HttpMethod -eq 'POST' -and $path -eq '/cleanup') {
        $before = $req.QueryString['before']
        if ($before -notmatch '^\d{4}-\d{2}-\d{2}$') { Send-Json $ctx 400 @{ error = 'Date invalide' }; return }
        # Seulement les fichiers créés par l'app (nom commençant par AAAA-MM-JJ_) et datés d'avant
        $removed = @()
        foreach ($sub in 'Workouts', 'NewFiles') {
            foreach ($file in Get-WatchFiles $watch $sub) {
                if ($file.Name -match '^(\d{4}-\d{2}-\d{2})_' -and $Matches[1] -lt $before) {
                    Move-WatchFileAway $watch $file
                    $removed += $file.Name
                    Write-Log "Séance passée retirée : $sub\$($file.Name)"
                }
            }
        }
        Send-Json $ctx 200 @{ removed = @($removed) }
        return
    }
    Send-Json $ctx 404 @{ error = 'Route inconnue' }
}

$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://localhost:$Port/")
try {
    $listener.Start()
} catch {
    Write-Log "Démarrage impossible sur le port $Port (déjà lancé ?) : $($_.Exception.Message)"
    exit 1
}
Write-Log "Relais démarré sur le port $Port$(if ($DossierTest) { " (dossier de test $DossierTest)" })"
while ($listener.IsListening) {
    $ctx = $listener.GetContext()
    try {
        Invoke-Route $ctx
    } catch {
        Write-Log "Erreur : $($_.Exception.Message)"
        try { Send-Json $ctx 500 @{ error = $_.Exception.Message } } catch {}
    }
}
