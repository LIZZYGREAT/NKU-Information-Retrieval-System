param(
    [ValidateSet("dev", "prod")]
    [string]$Env = "prod",
    [switch]$DryRun,
    [int]$Limit = 0,
    [string]$Url = ""
)
$env:ENV_TYPE = $Env
$root = Split-Path $PSScriptRoot -Parent
Set-Location "$root\backend"
$args = @()
if ($DryRun) { $args += "--dry-run" }
if ($Limit -gt 0) { $args += @("--limit", $Limit) }
if ($Url) { $args += @("--url", $Url) }
python scripts/clean_crawl_garbage.py @args
