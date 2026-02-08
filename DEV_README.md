# Development quick start

Two easy ways to run the full stack locally (frontend + backend):

1) npm script (cross-platform, uses `concurrently`)

From the repository root:

```cmd
npm install
npm run dev:all
```

This runs the frontend dev server (Vite) and the backend dev server (nodemon) concurrently in the same terminal.

2) Windows batch (opens two cmd windows)

You can use the included `start-dev.bat` which opens two new cmd windows (one for each server):

```cmd
start-dev.bat
```

Notes

- Make sure you have filled in environment files before starting the servers:
  - `backend/.env` (copy from `backend/.env.example`) — set `MONGODB_URI`, `JWT_SECRET`, etc.
  - `frontend/.env` (copy from `frontend/.env.example`) — set `VITE_API_URL` if needed.
- Frontend dev server: Vite with HMR (edits to `frontend/src/` are hot-reloaded).
- Backend dev server: nodemon auto-restarts on file changes in `backend/src/`.

Troubleshooting

- If `concurrently` is not installed, run `npm install` in the repo root.
- To stop the batch-launched servers, close their cmd windows.
