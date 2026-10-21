param([string]$Version = '')
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Source = Join-Path $Root 'Source'
if (-not $Version) {
    $Version = [regex]::Match((Get-Content "$Source/config.py" -Raw), '(?m)^VERSION\s*=\s*"([^"]+)"').Groups[1].Value
}
if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw 'Ungueltige Version' }
$Stage = Join-Path $Root "PublicBuild/Clean-$Version/JobScoutAI-Portable"
if (Test-Path -LiteralPath $Stage) { throw "Staging existiert bereits: $Stage" }
$Used = Join-Path $Root 'PublicBuild/JobScoutAI-Portable'
New-Item -ItemType Directory -Path $Stage -Force | Out-Null
# Only application files, never a used data directory or local credentials.
foreach ($Directory in '_internal', 'runtime', 'models', 'licenses') {
    robocopy "$Used/$Directory" "$Stage/$Directory" /E /R:1 /W:1 /NFL /NDL /NP | Out-Null
    if ($LASTEXITCODE -gt 7) { throw "Kopieren fehlgeschlagen: $Directory" }
}
foreach ($Name in 'JobScoutAI.exe', 'BUILD-INFO.txt', 'CHECKSUMS-SHA256.txt') {
    Copy-Item -LiteralPath "$Used/$Name" -Destination $Stage
}
Get-ChildItem "$Source/distribution" -File | Where-Object Extension -In '.md', '.txt' | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $Stage -Force
}
Copy-Item "$Source/distribution/licenses/*" "$Stage/licenses" -Recurse -Force
Copy-Item "$Used/runtime/ollama/lib/ollama/DLFCN_WIN32_COPYING" "$Stage/licenses/ollama-vendor" -Force
& "$Source/.venv/Scripts/python.exe" "$Source/developer_tools/audit_public_credentials.py" $Stage
if ($LASTEXITCODE -ne 0) { throw 'Zugangsdatenpruefung fehlgeschlagen' }
Write-Host "Sauberer Release-Ordner: $Stage"
