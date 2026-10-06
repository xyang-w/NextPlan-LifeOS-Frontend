# NextPlan local sync service

Temporary local adapter used to verify the browser-to-NextPlan flow while the private backend repository is unavailable.

```bash
python3 backend_local/server.py
```

Endpoints:

- `GET /health`
- `GET /api/state`
- `POST /api/chat/sync`

The adapter stores synced context as a Note in `backend_local/state.json`. It deliberately does not call OpenAI or expose an API key; the production backend should replace the note parser with a server-side GPT/tool-calling implementation.
