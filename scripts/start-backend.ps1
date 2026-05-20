param(
    [ValidateSet("dev", "prod")]
    [string]$Env = "dev"
)
$env:ENV_TYPE = $Env
$root = Split-Path $PSScriptRoot -Parent
python "$root\scripts\gen_frontend_config.py"
python "$root\scripts\run_backend.py"
