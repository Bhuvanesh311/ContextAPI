# ContextAPI Web

React 19 + Vite 8 frontend for the ContextAPI backend (`infer-ai_backend`):
dashboard, projects, knowledge (documents), target applications, reports,
settings, and the floating ContextAPI Assistant.

Needs Node 20.19+ or 22.12+.

## Run in development

```sh
npm install
npm run dev          # http://localhost:5173
```

The app calls the API at `/backend/*`. The Vite dev server proxies that to
FastAPI at `http://localhost:8000` (override with `BACKEND_URL=...`), so the
browser stays on one origin and the backend needs no CORS setup.
`VITE_API_BASE_URL` (see `.env.example`) defaults to `/backend`.

## Production (Docker)

```sh
docker compose up -d --build   # http://localhost:8080 (WEB_PORT to change)
```

nginx serves the build and proxies `/backend/*` to the `contextapi-app-api-1`
container on the `contextapi-network` network, so the backend stack must be up.
Uploads of up to 10 × 500 MB per request pass through without buffering.

## Assistant

- Answers appear live while they are written: the assistant polls
  `GET /api/v1/retrieval/requests/{id}/answer?wait_seconds=1` and shows the
  current stage and `partial_answer` until `done`.
- Each project has its own conversation (saved in this browser). Questions in
  one conversation share a `correlation_id`, so follow-ups use earlier turns.
- Modes: **Answer** (DEEP), **Answer+** (COLLABORATIVE, with a fallback model)
  and **Search** (STANDARD: passages only, no generated answer).
- Answers show citations and their sources; Stop cancels a running request.

Uploads anywhere in the app go through `src/services/uploads.js`, which checks
each file against the backend limits and sends them in batches of 10 with
progress.

## End-to-end test

Drives the locally installed Edge (or Chrome) with playwright-core; no browser
download. The account must be verified.

```sh
E2E_EMAIL=you@example.com E2E_PASSWORD=... npm run test:e2e
# E2E_URL=http://localhost:8080 to test the Docker build, E2E_HEADED=1 to watch
```

It creates a project, uploads a file, checks the answer streams in with
sources, a follow-up, saved history, Search mode and a project-page upload.
Screenshots go to `e2e/shots`.
