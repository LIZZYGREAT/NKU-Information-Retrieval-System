"""Backend runtime settings bridge.

The canonical configuration lives in config/env_settings.py.
This module keeps backend imports stable via:

    from app.core.config import settings
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[3]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.env_settings import settings

__all__ = ["settings"]
