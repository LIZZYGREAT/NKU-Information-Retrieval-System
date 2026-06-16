import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_TYPE = os.getenv("ENV_TYPE", "dev")

_ENV_DEFAULTS = {
    "dev": {
        "MYSQL_DATABASE": "nku_search_dev",
        "ES_INDEX_NAME": "nku_web_index_dev",
    },
    "prod": {
        "MYSQL_DATABASE": "nku_search_prod",
        "ES_INDEX_NAME": "nku_web_index_prod",
    },
}


def load_key_env() -> Optional[Path]:
    key_file = PROJECT_ROOT / ".env.key"
    if key_file.exists():
        load_dotenv(key_file, override=True)
        return key_file
    return None


def load_env() -> Path:
    env_file = PROJECT_ROOT / f".env.{ENV_TYPE}"
    if not env_file.exists():
        raise FileNotFoundError(f"环境文件不存在: {env_file}")
    load_dotenv(env_file, override=True)
    load_key_env()
    return env_file


load_env()


def _required(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise ValueError(f"缺少环境变量 {key}，请检查 .env.{ENV_TYPE}")
    return val


class Settings:
    ENV_TYPE: str = ENV_TYPE
    MYSQL_HOST: str = _required("MYSQL_HOST")
    MYSQL_USER: str = _required("MYSQL_USER")
    MYSQL_PASSWORD: str = _required("MYSQL_PASSWORD")
    MYSQL_DATABASE: str = os.environ.get("MYSQL_DATABASE") or _ENV_DEFAULTS[ENV_TYPE]["MYSQL_DATABASE"]
    ES_HOST: str = os.environ.get("ES_HOST", "http://localhost:9200")
    ES_INDEX_NAME: str = os.environ.get("ES_INDEX_NAME") or _ENV_DEFAULTS[ENV_TYPE]["ES_INDEX_NAME"]
    SECRET_KEY: str = _required("SECRET_KEY")
    DEBUG: bool = os.environ.get("DEBUG", "true" if ENV_TYPE == "dev" else "false").lower() == "true"
    API_HOST: str = os.environ.get("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.environ.get("API_PORT", "8000"))
    API_BASE_URL: str = os.environ.get(
        "API_BASE_URL", f"http://127.0.0.1:{os.environ.get('API_PORT', '8000')}/api"
    )
    CORS_ORIGINS: list = [
        o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()
    ]
    CORRECT_ENGINE_URL: str = os.environ.get("CORRECT_ENGINE_URL", "http://127.0.0.1:8080")
    DEEPSEEK_API_KEY: str = os.environ.get("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL: str = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL: str = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
    TAGGER_MODE: str = os.environ.get("TAGGER_MODE", "hybrid")
    TAGGER_MIN_CONFIDENCE: float = float(os.environ.get("TAGGER_MIN_CONFIDENCE", "0.55"))
    CRAWL_TAGGER_MODE: str = os.environ.get("CRAWL_TAGGER_MODE", "rule")
    BATCH_TAG_SIZE: int = int(os.environ.get("BATCH_TAG_SIZE", "8"))
    BATCH_TAG_WORKERS: int = int(os.environ.get("BATCH_TAG_WORKERS", "5"))
    DEEPSEEK_CALL_INTERVAL: float = float(os.environ.get("DEEPSEEK_CALL_INTERVAL", "0.35"))


settings = Settings()
