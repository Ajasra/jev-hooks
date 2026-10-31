$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$homeDir = [Environment]::GetFolderPath('UserProfile')

function Ensure-Junction([string]$Link, [string]$Target) {
    $parent = Split-Path -Parent $Link
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    if (Test-Path -LiteralPath $Link) {
        $item = Get-Item -LiteralPath $Link -Force
        $currentTarget = ($item.Target -join '')
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -and ($currentTarget -eq $Target -or (Resolve-Path $currentTarget).Path -eq (Resolve-Path $Target).Path)) {
            return
        }
        Write-Warning "Target already exists; leaving untouched: $Link"
        return
    }
    New-Item -ItemType Junction -Path $Link -Target $Target | Out-Null
}

function Add-JsonEntry($Object, [string]$Name, $Value) {
    if (-not $Object.PSObject.Properties[$Name]) {
        $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
    }
}

function Save-Json($Object, [string]$Path) {
    $Object | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $Path -Encoding UTF8
}

$skills = Get-ChildItem -LiteralPath (Join-Path $repo '.agents\skills') -Directory

# Make the canonical Jev skills available to projects without a local jev.json.
$jevConfigDir = Join-Path $env:APPDATA 'Jev'
New-Item -ItemType Directory -Force -Path $jevConfigDir | Out-Null
$jevConfigPath = Join-Path $jevConfigDir 'config.json'
if (Test-Path -LiteralPath $jevConfigPath) {
    $jevConfig = Get-Content -LiteralPath $jevConfigPath -Raw | ConvertFrom-Json
}
else {
    $jevConfig = [pscustomobject]@{}
}
$canonicalSkillRoot = Join-Path $repo '.agents\skills'
$globalSkillRoots = @($jevConfig.skill_roots | ForEach-Object { [string]$_ })
if ($globalSkillRoots -notcontains $canonicalSkillRoot) {
    Add-JsonEntry $jevConfig 'skill_roots' @()
    $jevConfig.skill_roots = @($globalSkillRoots + $canonicalSkillRoot)
    Save-Json $jevConfig $jevConfigPath
}

# Antigravity / Gemini user configuration
$antigravity = Join-Path $homeDir '.gemini\config'
Ensure-Junction (Join-Path $antigravity 'hooks') (Join-Path $repo '.agents\hooks')
Ensure-Junction (Join-Path $antigravity 'skills') (Join-Path $repo '.agents\skills')
Ensure-Junction (Join-Path $antigravity 'protocols') (Join-Path $repo '.agents\protocols')
$antigravityHooks = Join-Path $antigravity 'hooks.json'
$sourceHooks = Get-Content -LiteralPath (Join-Path $repo '.agents\hooks.json') -Raw | ConvertFrom-Json
if (Test-Path -LiteralPath $antigravityHooks) {
    $installedHooks = Get-Content -LiteralPath $antigravityHooks -Raw | ConvertFrom-Json
}
else {
    $installedHooks = [pscustomobject]@{}
}
$installedHooks | Add-Member -Force -NotePropertyName 'jev-runtime' -NotePropertyValue $sourceHooks.'jev-runtime'
Save-Json $installedHooks $antigravityHooks

$antigravityMcpPath = Join-Path $antigravity 'mcp_config.json'
if (Test-Path -LiteralPath $antigravityMcpPath) {
    $antigravityMcp = Get-Content -LiteralPath $antigravityMcpPath -Raw | ConvertFrom-Json
}
else {
    $antigravityMcp = [pscustomobject]@{ mcpServers = [pscustomobject]@{} }
}
if (-not $antigravityMcp.mcpServers) {
    Add-JsonEntry $antigravityMcp 'mcpServers' ([pscustomobject]@{})
}
Add-JsonEntry $antigravityMcp.mcpServers 'jev' ([pscustomobject]@{
    command = 'jev'
    args = @('mcp', '--harness', 'antigravity')
})
Save-Json $antigravityMcp $antigravityMcpPath

# Codex and Codex-based local harnesses
$codex = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $homeDir '.codex' }
$python = Get-Command python -ErrorAction Stop
$codexHookInstaller = Join-Path $repo 'scripts\codex_hooks.py'
& $python.Source $codexHookInstaller install --project $repo --codex-home $codex
if ($LASTEXITCODE -ne 0) {
    throw 'Codex hooks were not installed. Resolve the reported scope conflict and rerun this installer.'
}
$codexSkills = Join-Path $codex 'skills'
foreach ($skill in $skills) {
    Ensure-Junction (Join-Path $codexSkills $skill.Name) $skill.FullName
}

$codexConfig = Join-Path $codex 'config.toml'
$toml = Get-Content -LiteralPath $codexConfig -Raw
if ($toml -notmatch '(?m)^\[mcp_servers\.jev\]\s*$') {
    $nl = [string][char]13 + [char]10
    $block = $nl + '[mcp_servers.jev]' + $nl +
        'command = "jev"' + $nl +
        'args = ["mcp", "--harness", "codex"]' + $nl +
        'startup_timeout_sec = 10' + $nl +
        'tool_timeout_sec = 30' + $nl
    Add-Content -LiteralPath $codexConfig -Value $block -Encoding UTF8
}

# OpenCode: discover the local plugin and skills, then merge MCP and agent entries.
$openCode = Join-Path $homeDir '.config\opencode'
$openCodePlugin = Join-Path $openCode 'plugins\jev-plugin.js'
$openCodePluginParent = Split-Path -Parent $openCodePlugin
New-Item -ItemType Directory -Force -Path $openCodePluginParent | Out-Null
$openCodePluginMarker = "$openCodePlugin.jev-managed"
$pluginSource = Join-Path $repo '.agents\opencode\jev-plugin.js'
if (-not (Test-Path -LiteralPath $openCodePlugin)) {
    try {
        New-Item -ItemType SymbolicLink -Path $openCodePlugin -Target $pluginSource | Out-Null
    }
    catch {
        Copy-Item -LiteralPath $pluginSource -Destination $openCodePlugin
        Set-Content -LiteralPath $openCodePluginMarker -Value $pluginSource -Encoding UTF8
    }
}
elseif (Test-Path -LiteralPath $openCodePluginMarker) {
    $sourceContent = Get-Content -LiteralPath $pluginSource -Raw
    $installedContent = Get-Content -LiteralPath $openCodePlugin -Raw
    if ($sourceContent -cne $installedContent) {
        Copy-Item -LiteralPath $pluginSource -Destination $openCodePlugin -Force
    }
}
elseif ((Get-Content -LiteralPath $openCodePlugin -Raw).Contains('export default async function jevPlugin')) {
    # Refresh a Jev plugin previously copied by this installer version.
    Copy-Item -LiteralPath $pluginSource -Destination $openCodePlugin -Force
    Set-Content -LiteralPath $openCodePluginMarker -Value $pluginSource -Encoding UTF8
}
$openCodeSkills = Join-Path $openCode 'skills'
foreach ($skill in $skills) {
    Ensure-Junction (Join-Path $openCodeSkills $skill.Name) $skill.FullName
}

$openCodeConfigs = @('opencode.json', 'opencode.jsonc') | ForEach-Object { Join-Path $openCode $_ } |
    Where-Object { Test-Path -LiteralPath $_ }
if (-not $openCodeConfigs) {
    $newConfig = Join-Path $openCode 'opencode.json'
    New-Item -ItemType Directory -Force -Path $openCode | Out-Null
    Set-Content -LiteralPath $newConfig -Value '{}' -Encoding UTF8
    $openCodeConfigs = @($newConfig)
}
foreach ($path in $openCodeConfigs) {
    $config = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
    if (-not $config.mcp) {
        Add-JsonEntry $config 'mcp' ([pscustomobject]@{})
    }
    Add-JsonEntry $config.mcp 'jev' ([pscustomobject]@{
        type = 'local'
        command = @('jev', 'mcp', '--harness', 'opencode')
    })
    if (-not $config.agent) {
        Add-JsonEntry $config 'agent' ([pscustomobject]@{})
    }
    Add-JsonEntry $config.agent 'jev' ([pscustomobject]@{
        description = 'Jev shared safety, routing, and verification tools'
        mode = 'all'
        prompt = 'Use Jev System One hooks and shared runtime for safety, routing, and verification.'
    })
    Save-Json $config $path
}

Write-Output 'Jev installed for Antigravity, Codex, and OpenCode.'
