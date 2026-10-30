$ErrorActionPreference = 'Stop'
$installer = Join-Path $PSScriptRoot 'install-user-harnesses.ps1'
& $installer @args
exit $LASTEXITCODE
