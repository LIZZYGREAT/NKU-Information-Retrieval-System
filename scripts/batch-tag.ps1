param(
    [ValidateSet("dev", "prod")]
    [string]$Env = "dev",
    [int]$BatchSize = 8,
    [int]$Workers = 5,
    [int]$Limit = 0,
    [switch]$Status,
    [switch]$ResetProgress
)
$env:ENV_TYPE = $Env
$root = Split-Path $PSScriptRoot -Parent
Set-Location "$root\backend"
$pyArgs = @("--batch-size", $BatchSize, "--workers", $Workers)
if ($Limit -gt 0) { $pyArgs += @("--limit", $Limit) }
if ($Status) { $pyArgs += @("--status") }
if ($ResetProgress) { $pyArgs += @("--reset-progress") }
python scripts/batch_tag_worker.py @pyArgs
