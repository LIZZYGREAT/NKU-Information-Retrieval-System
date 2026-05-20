param(
    [ValidateSet("dev", "prod")]
    [string]$Env = "dev",
    [int]$Port = 5500
)
$env:ENV_TYPE = $Env
$root = Split-Path $PSScriptRoot -Parent
python "$root\scripts\gen_frontend_config.py"
Set-Location "$root\frontend"
python -m http.server $Port
