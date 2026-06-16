param(
    [ValidateSet("dev", "prod")]
    [string]$Env = "dev",
    [string]$Spider = "nankai_main",
    [switch]$Fresh
)
$env:ENV_TYPE = $Env
$root = Split-Path $PSScriptRoot -Parent
$jobDir = Join-Path "$root\crawler" "crawl_jobs\$Spider"

if ($Fresh -and (Test-Path $jobDir)) {
    Remove-Item -Recurse -Force $jobDir
    Write-Host "已清除断点，从头爬取"
} elseif (Test-Path $jobDir) {
    Write-Host "检测到断点，继续爬取: $jobDir"
} else {
    Write-Host "首次爬取"
}

Set-Location "$root\crawler"
scrapy crawl $Spider -s "JOBDIR=$jobDir"
