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
  - `mode` is required
- `GET /graviton-bridge/control/status` (worker identity + auth/config status)

Control-plane security for `POST /graviton-bridge/config`:
- requires HMAC headers:
  - `X-Graviton-Timestamp` (unix seconds)
  - `X-Graviton-Nonce` (unique request id)
  - `X-Graviton-Signature` (hex HMAC-SHA256)
- signature input: `METHOD\nPATH\nTIMESTAMP\nNONCE\nRAW_BODY`
- required env on worker:
  - `GRAVITON_BRIDGE_CONTROL_HMAC_SECRET`
  - optional: `GRAVITON_WORKER_ID`
  - optional: `GRAVITON_BRIDGE_CONTROL_MAX_SKEW_SECONDS` (default `60`)
  - optional: `GRAVITON_BRIDGE_CONTROL_NONCE_TTL_SECONDS` (default `300`)

Minimal control-plane examples:

```bash
# Worker status (identity + config/auth state)
curl "http://<worker>/graviton-bridge/control/status"

# Signed config update (mode + provider settings)
BODY='{"mode":"s3","s3":{"bucket":"my-bucket","region":"us-east-1","prefix":"graviton","access_key":"AKIA...","secret_key":"..."}}'
TS=$(date +%s)
NONCE=$(uuidgen | tr 'A-Z' 'a-z')
MSG=$(printf 'POST\n/graviton-bridge/config\n%s\n%s\n%s' "$TS" "$NONCE" "$BODY")
SIG=$(printf '%s' "$MSG" | openssl dgst -sha256 -hmac "$GRAVITON_BRIDGE_CONTROL_HMAC_SECRET" -hex | awk '{print $2}')

curl -X POST "http://<worker>/graviton-bridge/config" \
  -H "Content-Type: application/json" \
  -H "X-Graviton-Timestamp: $TS" \
  -H "X-Graviton-Nonce: $NONCE" \
  -H "X-Graviton-Signature: $SIG" \
  -d "$BODY"
```

Provider config source rule: if `config.json` exists, bridge uses only config file values; if `config.json` does not exist, bridge falls back to provider env vars.

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
