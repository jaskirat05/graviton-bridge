# graviton_bridge (Comfy custom-node package)

This package provides:
- template file hosting endpoints under this custom node directory
- a lightweight iframe bridge extension for workflow import/export

## Install on Comfy server

Clone this repo into Comfy's custom nodes path:

```bash
cd <COMFY_ROOT>/custom_nodes
git clone <YOUR_GIT_REMOTE_URL> graviton_bridge
```

Restart ComfyUI.

### Routes

- `GET /graviton-bridge/templates` (list files in `custom_nodes/graviton_bridge/templates`)
- `GET /graviton-bridge/templates/download/{filename}` (download one `.json`/`.flow`)
- `POST /graviton-bridge/templates/upload`:
  - `multipart/form-data` with field `file`, or
  - JSON `{ "filename": "my_template.json", "content": "{...}" }`
