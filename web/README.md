# Web (Static)

The web UI is static HTML/CSS/JS and talks to the engine via `ENGINE_BASE_URL`.

## Configure

Set `window.RUNTIME_CONFIG.ENGINE_BASE_URL` (recommended) or leave empty to use same-origin:

- Local: edit `web/static/runtime-config.js`
- Container: set `ENGINE_BASE_URL` env (Docker entrypoint rewrites runtime-config.js)

## Run

```bash
python -m http.server 5173 --directory web
```

Then open:

- `http://127.0.0.1:5173/ask`
- `http://127.0.0.1:5173/admin`
