param([string]$AiAssets = '', [string]$GuiBuild = '')
# One fresh build, from public sources and explicitly selected model/runtime files.
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'PublicBuild_erstellen.ps1') -AiAssets $AiAssets -GuiBuild $GuiBuild
if ($LASTEXITCODE -ne 0) { throw 'Release-Vorbereitung fehlgeschlagen' }
