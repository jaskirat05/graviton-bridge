from __future__ import annotations

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
WEB_DIRECTORY = "./web"

LOCAL_TEMPLATES_DIR = ROOT_DIR / "templates"
ALLOWED_TEMPLATE_SUFFIXES = {".json", ".flow"}
