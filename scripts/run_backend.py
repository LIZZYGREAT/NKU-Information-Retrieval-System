import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)
os.environ["PYTHONPATH"] = os.pathsep.join(
    [str(BACKEND_DIR), str(ROOT), os.environ.get("PYTHONPATH", "")]
).strip(os.pathsep)

from config.env_settings import settings
import uvicorn

if __name__ == "__main__":
    use_reload = settings.DEBUG and sys.platform != "win32"
    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=use_reload,
        reload_dirs=[str(BACKEND_DIR)] if use_reload else None,
    )
