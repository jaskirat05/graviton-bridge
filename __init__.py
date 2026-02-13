from __future__ import annotations

from .constants import LOCAL_TEMPLATES_DIR, WEB_DIRECTORY
from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

# Register routes via side-effect imports.
from . import asset_routes as _asset_routes  # noqa: F401
from . import config_routes as _config_routes  # noqa: F401
from . import template_routes as _template_routes  # noqa: F401

LOCAL_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
