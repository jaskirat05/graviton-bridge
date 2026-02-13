# graviton_bridge (Comfy custom-node package)

This package provides:
- template file hosting endpoints under this custom node directory
- a lightweight iframe bridge extension for workflow import/export
- local asset endpoints for bridge I/O
- Graviton load/save custom nodes for image/text/file/video/audio/3d

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

- `GET /graviton-bridge/assets` (list stored assets metadata)
- `GET /graviton-bridge/assets/{asset_id}/meta`
- `GET /graviton-bridge/assets/{asset_id}` (download asset bytes)
- `POST /graviton-bridge/assets/upload?kind=image|video|audio|text|3d|file`
  - `multipart/form-data` with field `file`

- `GET /graviton-bridge/config` (effective config, secrets redacted)
- `POST /graviton-bridge/config` (persist config to `custom_nodes/graviton_bridge/config.json`)
  - accepts either raw config object or `{ "config": { ... } }`
  - accepts partial patch payloads (deep-merged with current config)
  - requires env `GRAVITON_PAIRING_TOKEN` on server
  - caller must send matching token via:
    - `Authorization: Bearer <token>`, or
    - `X-Graviton-Pairing-Token: <token>`

Minimal control-plane examples:

```bash
# Set local/orchestrator mode (parent URL comes from bridge env)
curl -X POST "http://<child>/graviton-bridge/config" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <PAIRING_TOKEN>" \
  -d '{"mode":"local"}'

# Switch to s3 mode
curl -X POST "http://<child>/graviton-bridge/config" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <PAIRING_TOKEN>" \
  -d '{"mode":"s3"}'

# Switch to cloudinary mode
curl -X POST "http://<child>/graviton-bridge/config" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <PAIRING_TOKEN>" \
  -d '{"mode":"cloudinary"}'
```

### S3 provider mode

- Set bridge config `mode` to `s3`.
- Requires `boto3` + `botocore` installed in the Comfy Python env.
- Configure S3 connection in bridge env:
  - `GRAVITON_S3_BUCKET` (required)
  - `GRAVITON_S3_REGION` (required)
  - `GRAVITON_S3_ACCESS_KEY` (required)
  - `GRAVITON_S3_SECRET_KEY` (required)
  - `GRAVITON_S3_PREFIX` (optional)

### Orchestrator provider env

- For `mode=local`/`mode=orchestrator`, bridge reads:
  - `GRAVITON_ORCHESTRATOR_BASE_URL` (required)
  - `GRAVITON_ORCHESTRATOR_TOKEN` (optional)

### Cloudinary provider env

- Set bridge config `mode` to `cloudinary`.
- Configure Cloudinary connection in bridge env:
  - `GRAVITON_CLOUDINARY_CLOUD_NAME` (required)
  - `GRAVITON_CLOUDINARY_API_KEY` (required)
  - `GRAVITON_CLOUDINARY_API_SECRET` (required)
  - `GRAVITON_CLOUDINARY_FOLDER` (optional)

### Nodes

- Save nodes now return two outputs: `asset_id` and serialized canonical `asset_ref` JSON.
- Load nodes accept a single `asset_ref` string input:
  - plain `asset_id`, or
  - full serialized canonical `asset_ref` JSON.

- `GravitonSaveImage` / `GravitonLoadImage`
- `GravitonSaveText` / `GravitonLoadText`
- `GravitonSaveFile` / `GravitonLoadFile`
- `GravitonSaveVideo` / `GravitonLoadVideo` (path-based payload handling for now)
- `GravitonSaveAudio` / `GravitonLoadAudio` (path-based payload handling for now)
- `GravitonSave3D` / `GravitonLoad3D` (path-based payload handling for now)
