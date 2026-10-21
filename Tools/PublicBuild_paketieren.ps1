param(
    [string]$SevenZip = "C:\Program Files\7-Zip\7z.exe",
    [string]$BuildPath = ''
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$PublicRoot = Join-Path $Root "PublicBuild"
$Build = Join-Path $PublicRoot "JobScoutAI-Portable"
if ($BuildPath) { $Build = [IO.Path]::GetFullPath($BuildPath) }
$ConfigText = Get-Content -LiteralPath (Join-Path $Root "Source\config.py") -Raw
$Version = [regex]::Match($ConfigText, '(?m)^VERSION\s*=\s*"([^"]+)"').Groups[1].Value
if (-not $Version) { throw "VERSION fehlt in Source/config.py." }
$Assets = Join-Path $PublicRoot "ReleaseAssets-$Version"
$ArchiveName = "JobScoutAI-Portable-$Version.7z"

if (-not (Test-Path -LiteralPath (Join-Path $Build "JobScoutAI.exe") -PathType Leaf)) {
    throw "Standalone-Build fehlt: $Build"
}
if ((Test-Path -LiteralPath (Join-Path $Build '.env')) -or (Get-ChildItem -LiteralPath (Join-Path $Build 'data') -Recurse -File -ErrorAction SilentlyContinue)) {
    throw 'Dieser Ordner wurde bereits benutzt. Fuer die Weitergabe zuerst einen frischen PublicBuild ohne .env und Nutzerdaten erstellen.'
}
if (-not (Test-Path -LiteralPath $SevenZip -PathType Leaf)) {
    throw "7-Zip wurde nicht gefunden: $SevenZip"
}

$PublicRootPath = [IO.Path]::GetFullPath($PublicRoot).TrimEnd([IO.Path]::DirectorySeparatorChar)
$AssetsPath = [IO.Path]::GetFullPath($Assets)
if (-not $AssetsPath.StartsWith($PublicRootPath + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Unsicherer Zielpfad: $AssetsPath"
}
if (Test-Path -LiteralPath $Assets) { throw "Release-Ordner existiert bereits: $Assets" }
New-Item -ItemType Directory -Force -Path $Assets | Out-Null

Push-Location (Split-Path -Parent $Build)
try {
    & $SevenZip a -t7z -mx=1 -mmt=on (Join-Path $Assets $ArchiveName) (Split-Path -Leaf $Build)
    if ($LASTEXITCODE -ne 0) { throw "7-Zip-Paketierung ist fehlgeschlagen." }
} finally {
    Pop-Location
}

$ArchivePath = Join-Path $Assets $ArchiveName
$InputStream = [IO.File]::OpenRead($ArchivePath)
try {
    $HalfSize = [long][Math]::Ceiling($InputStream.Length / 2.0)
    $Buffer = New-Object byte[] (4MB)
    foreach ($Part in 1..2) {
        $PartPath = "$ArchivePath.{0:D3}" -f $Part
        $OutputStream = [IO.File]::Create($PartPath)
        try {
            $Remaining = [Math]::Min($HalfSize, $InputStream.Length - $InputStream.Position)
            while ($Remaining -gt 0) {
                $Read = $InputStream.Read($Buffer, 0, [int][Math]::Min($Buffer.Length, $Remaining))
                if ($Read -eq 0) { throw "Unerwartetes Archivende." }
                $OutputStream.Write($Buffer, 0, $Read)
                $Remaining -= $Read
            }
        } finally { $OutputStream.Dispose() }
    }
} finally { $InputStream.Dispose() }

$FirstVolume = Join-Path $Assets "$ArchiveName.001"
& $SevenZip t $FirstVolume
if ($LASTEXITCODE -ne 0) { throw "Das geteilte Release-Archiv ist beschaedigt." }
Remove-Item -LiteralPath $ArchivePath -Force

$Volumes = Get-ChildItem -LiteralPath $Assets -Filter "$ArchiveName.*" -File | Sort-Object Name
if (-not $Volumes -or ($Volumes | Where-Object Length -GE 2GB)) {
    throw "Mindestens ein Release-Teil fehlt oder ueberschreitet die GitHub-Grenze von 2 GiB."
}

$Hinweis = @"
JobScout AI Portable $Version herunterladen
============================================

1. Alle Dateien mit den Endungen .7z.001 und .7z.002 in denselben Ordner laden.
2. Die Datei .7z.001 mit 7-Zip oeffnen und entpacken.
3. Im entpackten Ordner JobScoutAI.exe starten. Eine Installation ist nicht erforderlich.

Beide Archivteile gehoeren zusammen. Die Pruefsummen stehen in
RELEASE-ASSETS-SHA256.txt.
"@
Set-Content -LiteralPath (Join-Path $Assets "DOWNLOAD-HINWEIS.txt") -Value $Hinweis -Encoding UTF8

$HashLines = foreach ($File in $Volumes) {
    $Hash = Get-FileHash -LiteralPath $File.FullName -Algorithm SHA256
    "$($Hash.Hash.ToLowerInvariant())  $($File.Name)"
}
Set-Content -LiteralPath (Join-Path $Assets "RELEASE-ASSETS-SHA256.txt") -Value $HashLines -Encoding ASCII

Write-Host "GitHub-Release-Dateien erstellt und geprueft:"
$Volumes | ForEach-Object { Write-Host ("{0} ({1:N2} GB)" -f $_.FullName, ($_.Length / 1GB)) }
