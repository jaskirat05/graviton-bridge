# graviton_bridge (Comfy custom-node package)

This package provides:
- dynamic template directory registration (without editing `folder_paths.py`)
- a lightweight iframe bridge extension for workflow import/export

## Install on Comfy server

Clone this repo into Comfy's custom nodes path:

```bash
cd <COMFY_ROOT>/custom_nodes
git clone <YOUR_GIT_REMOTE_URL> graviton_bridge
```

Restart ComfyUI.

## Template directory management

On startup, the package auto-registers:
- `<this package>/templates`



### Routes

- `GET /graviton-bridge/templates/paths`
- `POST /graviton-bridge/templates/add` with JSON body `{ "path": "/abs/path", "is_default": false }`
- `GET /graviton-bridge/templates/files`
- `GET /graviton-bridge/templates/files?path=/abs/path`


