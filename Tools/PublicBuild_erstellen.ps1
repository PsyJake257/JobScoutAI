param(
    [string]$OllamaInstall = "$env:LOCALAPPDATA\Programs\Ollama",
    [string]$OllamaModelStore = "$env:USERPROFILE\.ollama\models"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Source = Join-Path $Root "Source"
$Python = Join-Path $Source ".venv\Scripts\python.exe"
$PublicRoot = Join-Path $Root "PublicBuild"
$Target = Join-Path $PublicRoot "JobScoutAI-Portable"
$BuildRoot = Join-Path $Root "Backups\public_build_candidate"
$OllamaExe = Join-Path $OllamaInstall "ollama.exe"
$OllamaLib = Join-Path $OllamaInstall "lib\ollama"
$ModelManifest = Join-Path $OllamaModelStore "manifests\registry.ollama.ai\library\qwen3\4b"

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Python-Umgebung fehlt: $Python" }
if (-not (Test-Path -LiteralPath $OllamaExe -PathType Leaf)) { throw "Ollama-Laufzeit fehlt: $OllamaExe" }
if (-not (Test-Path -LiteralPath $OllamaLib -PathType Container)) { throw "Ollama-Bibliotheken fehlen: $OllamaLib" }
if (-not (Test-Path -LiteralPath $ModelManifest -PathType Leaf)) { throw "Qwen3-4B-Modell fehlt: $ModelManifest" }

New-Item -ItemType Directory -Force -Path $PublicRoot | Out-Null
$PublicRootPath = [IO.Path]::GetFullPath($PublicRoot).TrimEnd([IO.Path]::DirectorySeparatorChar)
$TargetPath = [IO.Path]::GetFullPath($Target)
if (-not $TargetPath.StartsWith($PublicRootPath + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Unsicherer Zielpfad: $TargetPath"
}
$BackupsRootPath = [IO.Path]::GetFullPath((Join-Path $Root "Backups")).TrimEnd([IO.Path]::DirectorySeparatorChar)
$BuildRootPath = [IO.Path]::GetFullPath($BuildRoot)
if (-not $BuildRootPath.StartsWith($BackupsRootPath + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Unsicherer temporaerer Buildpfad: $BuildRootPath"
}

if (Test-Path -LiteralPath $BuildRoot) { Remove-Item -LiteralPath $BuildRoot -Recurse -Force }
New-Item -ItemType Directory -Force -Path $BuildRoot | Out-Null

Push-Location $Source
try {
    & $Python -m PyInstaller --noconfirm --clean --distpath (Join-Path $BuildRoot "dist") --workpath (Join-Path $BuildRoot "build") "JobScoutAI.spec"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller fehlgeschlagen mit Exitcode $LASTEXITCODE" }
} finally {
    Pop-Location
}

$Candidate = Join-Path $BuildRoot "dist\JobScoutAI"
if (-not (Test-Path -LiteralPath (Join-Path $Candidate "JobScoutAI.exe") -PathType Leaf)) {
    throw "Der Build-Kandidat enthaelt keine JobScoutAI.exe."
}

if (Test-Path -LiteralPath $Target) {
    $PublicBackup = Join-Path $Root ("Backups\PublicBuild_before_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
    Move-Item -LiteralPath $Target -Destination $PublicBackup
}
New-Item -ItemType Directory -Force -Path $Target | Out-Null
robocopy $Candidate $Target /E /COPY:DAT /R:1 /W:1 /NFL /NDL /NP | Out-Null
if ($LASTEXITCODE -gt 7) { throw "Kopieren des App-Builds ist fehlgeschlagen." }

$RuntimeTarget = Join-Path $Target "runtime\ollama"
$RuntimeLibTarget = Join-Path $RuntimeTarget "lib\ollama"
New-Item -ItemType Directory -Force -Path $RuntimeLibTarget | Out-Null
Copy-Item -LiteralPath $OllamaExe -Destination (Join-Path $RuntimeTarget "ollama.exe") -Force
Get-ChildItem -LiteralPath $OllamaLib -File | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $RuntimeLibTarget $_.Name) -Force
}

$ManifestData = Get-Content -LiteralPath $ModelManifest -Raw | ConvertFrom-Json
$ModelManifestTarget = Join-Path $Target "models\manifests\registry.ollama.ai\library\qwen3"
$ModelBlobTarget = Join-Path $Target "models\blobs"
New-Item -ItemType Directory -Force -Path $ModelManifestTarget, $ModelBlobTarget | Out-Null
Copy-Item -LiteralPath $ModelManifest -Destination (Join-Path $ModelManifestTarget "4b") -Force

$Digests = @($ManifestData.config.digest) + @($ManifestData.layers.digest)
foreach ($Digest in $Digests) {
    $BlobName = $Digest -replace ":", "-"
    $BlobSource = Join-Path (Join-Path $OllamaModelStore "blobs") $BlobName
    if (-not (Test-Path -LiteralPath $BlobSource -PathType Leaf)) { throw "Modellbestandteil fehlt: $BlobSource" }
    Copy-Item -LiteralPath $BlobSource -Destination (Join-Path $ModelBlobTarget $BlobName) -Force
}

$Distribution = Join-Path $Source "distribution"
$Licenses = Join-Path $Target "licenses"
New-Item -ItemType Directory -Force -Path $Licenses | Out-Null
Copy-Item -LiteralPath (Join-Path $Distribution "THIRD_PARTY_NOTICES.md") -Destination $Target -Force
Copy-Item -LiteralPath (Join-Path $Distribution "README_FIRST_START.txt") -Destination $Target -Force
Copy-Item -LiteralPath (Join-Path $Distribution "PRIVACY.md") -Destination $Target -Force
foreach ($Name in 'COMPONENTS.md', 'REDISTRIBUTION_TERMS.md') {
    Copy-Item -LiteralPath (Join-Path $Distribution $Name) -Destination $Target -Force
}
Copy-Item (Join-Path $Distribution 'licenses\*') -Destination $Licenses -Recurse -Force
Copy-Item -LiteralPath (Join-Path $Distribution "LICENSE-JOBSCOUT-AI.txt") -Destination $Licenses -Force
Copy-Item -LiteralPath (Join-Path $Distribution "OLLAMA-LICENSE.txt") -Destination $Licenses -Force

$QwenLicenseLayer = $ManifestData.layers | Where-Object mediaType -eq "application/vnd.ollama.image.license" | Select-Object -First 1
if ($null -eq $QwenLicenseLayer) { throw "Das Qwen3-Modell enthaelt keinen Lizenz-Layer." }
$QwenLicenseBlob = Join-Path (Join-Path $OllamaModelStore "blobs") ($QwenLicenseLayer.digest -replace ":", "-")
Copy-Item -LiteralPath $QwenLicenseBlob -Destination (Join-Path $Licenses "QWEN3-APACHE-2.0.txt") -Force

$PythonBase = & $Python -c "import sys; print(sys.base_prefix)"
Copy-Item -LiteralPath (Join-Path $PythonBase "LICENSE.txt") -Destination (Join-Path $Licenses "PYTHON-LICENSE.txt") -Force
Copy-Item -LiteralPath (Join-Path $PythonBase "tcl\tk8.6\license.terms") -Destination (Join-Path $Licenses "TCL-TK-LICENSE.txt") -Force
Copy-Item -LiteralPath (Join-Path $Source ".venv\Lib\site-packages\customtkinter-6.0.0.dist-info\licenses\LICENSE") -Destination (Join-Path $Licenses "CUSTOMTKINTER-LICENSE.txt") -Force
Copy-Item -LiteralPath (Join-Path $Source ".venv\Lib\site-packages\darkdetect-0.8.0.dist-info\LICENSE") -Destination (Join-Path $Licenses "DARKDETECT-LICENSE.txt") -Force
Copy-Item -LiteralPath (Join-Path $Source ".venv\Lib\site-packages\pillow-12.3.0.dist-info\licenses\LICENSE") -Destination (Join-Path $Licenses "PILLOW-LICENSE.txt") -Force
Copy-Item -LiteralPath (Join-Path $Source ".venv\Lib\site-packages\pyinstaller-6.21.0.dist-info\licenses\COPYING.txt") -Destination (Join-Path $Licenses "PYINSTALLER-COPYING.txt") -Force

$VendorLicenseTarget = Join-Path $Licenses "ollama-vendor"
New-Item -ItemType Directory -Force -Path $VendorLicenseTarget | Out-Null
Get-ChildItem -LiteralPath $OllamaLib -File | Where-Object Name -Match "LICENSE|COPYING|NOTICE" | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $VendorLicenseTarget $_.Name) -Force
}

$ConfigText = Get-Content -LiteralPath (Join-Path $Source "config.py") -Raw
$VersionMatch = [regex]::Match($ConfigText, '(?m)^VERSION\s*=\s*"([^"]+)"')
if (-not $VersionMatch.Success) { throw "VERSION konnte nicht aus Source/config.py gelesen werden." }
$Version = $VersionMatch.Groups[1].Value
$BuildInfo = @"
JobScout AI Portable $Version
Build date: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss K")
Architecture: Windows x64, CPU-compatible Ollama runtime
Local model: qwen3:4b (Q4_K_M, fully bundled)
Personal data and API keys: not included
"@
Set-Content -LiteralPath (Join-Path $Target "BUILD-INFO.txt") -Value $BuildInfo -Encoding UTF8

$ChecksumFiles = @(
    Join-Path $Target "JobScoutAI.exe"
    Join-Path $RuntimeTarget "ollama.exe"
    Join-Path $ModelManifestTarget "4b"
) + ($Digests | ForEach-Object { Join-Path $ModelBlobTarget ($_ -replace ":", "-") })
$ChecksumLines = foreach ($File in $ChecksumFiles) {
    $Hash = Get-FileHash -LiteralPath $File -Algorithm SHA256
    $Relative = [IO.Path]::GetRelativePath($Target, $File)
    "$($Hash.Hash.ToLowerInvariant())  $Relative"
}
Set-Content -LiteralPath (Join-Path $Target "CHECKSUMS-SHA256.txt") -Value $ChecksumLines -Encoding ASCII

& $Python (Join-Path $Source "developer_tools\audit_public_credentials.py") $Target
if ($LASTEXITCODE -ne 0) { throw "Zugangsdaten-Pruefung fehlgeschlagen; Build darf nicht weitergegeben werden." }
if (Get-ChildItem -LiteralPath (Join-Path $Target "data") -Recurse -File -ErrorAction SilentlyContinue) {
    throw "Der oeffentliche Build enthaelt unerwartete Nutzerdaten."
}

$Size = (Get-ChildItem -LiteralPath $Target -Recurse -File | Measure-Object Length -Sum).Sum
Write-Host "Standalone-Build erstellt:"
Write-Host $Target
Write-Host ("Groesse: {0:N2} GB" -f ($Size / 1GB))
