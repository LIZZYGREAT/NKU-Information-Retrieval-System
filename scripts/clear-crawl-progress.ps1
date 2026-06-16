param(
    [string]$Spider = "nankai_main"
)
$root = Split-Path $PSScriptRoot -Parent
$jobDir = Join-Path "$root\crawler" "crawl_jobs\$Spider"
if (Test-Path $jobDir) {
    Remove-Item -Recurse -Force $jobDir
    Write-Host "已清除断点: $jobDir"
} else {
    Write-Host "无断点目录: $jobDir"
}
