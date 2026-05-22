param(
    [ValidateSet("dev", "prod")]
    [string]$Env = "dev",
    [string]$Spider = "nankai_main"
)
$env:ENV_TYPE = $Env
$root = Split-Path $PSScriptRoot -Parent
Set-Location "$root\crawler"
scrapy crawl $Spider
