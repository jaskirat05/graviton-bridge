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

You can also provide extra template directories via env var:
- `GRAVITON_TEMPLATE_DIRS=/abs/path/one:/abs/path/two`

(`:` separator on Linux/macOS; use platform `os.pathsep` rules on Windows.)

### Routes

- `GET /graviton-bridge/templates/paths`
- `POST /graviton-bridge/templates/add` with JSON body `{ "path": "/abs/path", "is_default": false }`
- `GET /graviton-bridge/templates/files`
- `GET /graviton-bridge/templates/files?path=/abs/path`

## Iframe bridge extension

The extension script is exposed via `WEB_DIRECTORY` and loads automatically as:
- `/extensions/graviton_bridge/graviton-bridge.js`

Message contract:

From host -> iframe (`window.postMessage`):
- `{ source: "graviton-host", type: "ping" }`
- `{ source: "graviton-host", type: "import-workflow", payload: { workflow } }`
- `{ source: "graviton-host", type: "export-workflow" }`

From iframe -> host:
- `{ source: "graviton-bridge", type: "ready", payload: { version, hasGraph } }`
- `{ source: "graviton-bridge", type: "pong", payload: { now } }`
- `{ source: "graviton-bridge", type: "workflow-imported", payload: { workflow } }`
- `{ source: "graviton-bridge", type: "workflow-exported", payload: { workflow } }`
- `{ source: "graviton-bridge", type: "error", payload: { stage, message } }`

## Publish this package as a separate git repo

From `codex/graviton_bridge`:

```bash
git init
git add .
git commit -m "Initial graviton bridge custom node package"
git remote add origin <YOUR_REMOTE_URL>
git push -u origin main
```
