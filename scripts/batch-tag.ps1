param(
    [int]$BatchSize = 8,
    [int]$Workers = 5,
    [int]$Limit = 0
)
$root = Split-Path $PSScriptRoot -Parent
Set-Location "$root\backend"
$args = @("--batch-size", $BatchSize, "--workers", $Workers)
if ($Limit -gt 0) { $args += @("--limit", $Limit) }
python scripts/batch_tag_worker.py @args
