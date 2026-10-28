param([string]$AiAssets = '', [string]$GuiBuild = '', [string]$OutputPath = '')
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Source = Join-Path $Root 'Source'
$Python = Join-Path $Source '.venv/Scripts/python.exe'
$Version = [regex]::Match((Get-Content "$Source/config.py" -Raw), '(?m)^VERSION\s*=\s*"([^"]+)"').Groups[1].Value
if (-not $Version) { throw 'VERSION fehlt in Source/config.py' }
if (-not $AiAssets) { $AiAssets = Join-Path $Root 'ExternalAssets/Gemma4-E2B' }
if (-not $OutputPath) { $OutputPath = Join-Path $Root "PublicBuild/Clean-$Version/JobScoutAI-Portable" }
$Target = [IO.Path]::GetFullPath($OutputPath)
$AllowedRoot = [IO.Path]::GetFullPath((Join-Path $Root 'PublicBuild')).TrimEnd('\') + '\'
if (-not $Target.StartsWith($AllowedRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Build-Ziel muss unter PublicBuild liegen' }
if (Test-Path -LiteralPath $Target) { throw "Ziel existiert bereits: $Target" }
$Distribution = Join-Path $Source 'distribution'
$Provenance = Get-Content "$Distribution/MODEL-PROVENANCE.json" -Raw | ConvertFrom-Json
$Model = Join-Path $AiAssets ('models/' + $Provenance.file)
if (-not (Test-Path -LiteralPath $Model)) { throw 'Gemma-GGUF fehlt; AiAssets muss models und runtime enthalten' }
if ((Get-FileHash -LiteralPath $Model -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Provenance.sha256) { throw 'Gemma-Modell stimmt nicht mit der dokumentierten Herkunft überein' }
foreach ($Backend in 'cpu','vulkan') {
    if (-not (Test-Path -LiteralPath "$AiAssets/runtime/$Backend/llama-server.exe")) { throw "Laufzeit fehlt: $Backend" }
}
if (-not $GuiBuild) {
    $BuildRoot = Join-Path $Root ("Backups/main_build_" + $Version + '_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
    Push-Location $Source
    try {
        & $Python -m PyInstaller --noconfirm --distpath "$BuildRoot/dist" --workpath "$BuildRoot/build" JobScoutAI.spec
        if ($LASTEXITCODE -ne 0) { throw 'GUI-Build fehlgeschlagen' }
    } finally { Pop-Location }
    $GuiBuild = "$BuildRoot/dist/JobScoutAI"
}
if (-not (Test-Path -LiteralPath "$GuiBuild/JobScoutAI.exe")) { throw 'GUI-EXE fehlt' }
New-Item -ItemType Directory -Path $Target -Force | Out-Null
# Explicit allowlist: never copy user data, .env or test reports from AiAssets.
& robocopy "$GuiBuild/_internal" "$Target/_internal" /E /R:0 /W:0 /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw 'GUI-Kopie fehlgeschlagen' }
Copy-Item -LiteralPath "$GuiBuild/JobScoutAI.exe" -Destination $Target
& robocopy "$AiAssets/runtime" "$Target/runtime" /E /R:0 /W:0 /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw 'Laufzeit-Kopie fehlgeschlagen' }
New-Item -ItemType Directory -Path "$Target/models", "$Target/licenses" -Force | Out-Null
Copy-Item -LiteralPath $Model -Destination "$Target/models"
foreach ($Name in 'THIRD_PARTY_NOTICES.md','COMPONENTS.md','PRIVACY.md','REDISTRIBUTION_TERMS.md','README_FIRST_START.txt','MODEL-PROVENANCE.json') {
    Copy-Item -LiteralPath "$Distribution/$Name" -Destination $Target
}
Copy-Item -LiteralPath "$Distribution/LICENSE-JOBSCOUT-AI.txt" -Destination "$Target/licenses"
Get-ChildItem -LiteralPath "$Distribution/licenses" | Where-Object { $_.Name -notin 'ollama-vendor','OLLAMA-LICENSE.txt','QWEN3-APACHE-2.0.txt' } | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination "$Target/licenses" -Recurse -Force
}
if (-not (Test-Path -LiteralPath "$Target/licenses/GEMMA4_E2B_LICENSE.txt")) { throw 'Gemma-Lizenz fehlt' }
$BuildInfo = @"
JobScout AI Portable $Version
Build date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss K')
Architecture: Windows x64, llama.cpp Vulkan with CPU startup fallback
Local model: Gemma 4 E2B IT Q4_K_M (fully bundled)
Warmup: background model load and small inference at startup
Analysis: all selected jobs screened, detail conclusions on up to 15 candidates
Appearance: static frosted glass surfaces, no live blur
Personal data and API keys: not included
"@
Set-Content -LiteralPath "$Target/BUILD-INFO.txt" -Value $BuildInfo -Encoding utf8
$Hashes = foreach ($File in @((Get-Item "$Target/JobScoutAI.exe")) + @(Get-ChildItem "$Target/runtime" -File -Recurse) + @((Get-Item "$Target/models/$($Provenance.file)"))) {
    $Relative = [IO.Path]::GetRelativePath($Target, $File.FullName)
    $Hash = if ($Relative -eq ('models\' + $Provenance.file)) { $Provenance.sha256 } else { (Get-FileHash -LiteralPath $File.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
    "$Hash  $Relative"
}
Set-Content -LiteralPath "$Target/CHECKSUMS-SHA256.txt" -Value $Hashes -Encoding ascii
& $Python "$Source/developer_tools/audit_public_credentials.py" $Target
if ($LASTEXITCODE -ne 0) { throw 'Zugangsdatenprüfung fehlgeschlagen' }
if ((Test-Path -LiteralPath "$Target/.env") -or (Get-ChildItem "$Target/data" -Recurse -File -ErrorAction SilentlyContinue)) { throw 'Unerwartete persönliche Dateien im Build' }
Write-Output "Sauberer portabler Build: $Target"
exit 0
