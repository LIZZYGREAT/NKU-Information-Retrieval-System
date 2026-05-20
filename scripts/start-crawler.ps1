param(
    [ValidateSet("dev", "prod")]
    [string]$Env = "dev",
    [string]$Spider = "nku_resource"
)
$env:ENV_TYPE = $Env
$root = Split-Path $PSScriptRoot -Parent
Set-Location "$root\crawler"
scrapy crawl $Spider
