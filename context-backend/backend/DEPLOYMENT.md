# ContextAPI — Offline Deployment & Swagger Test Guide

Runs the whole backend in Docker with **no internet at runtime**: the LLM is Ollama on the host, the embedding/reranker models are loaded from a local volume, and external LLMs (Tier C) stay off unless API keys are set.

Commands assume **PowerShell** on Windows (Docker Desktop). On Linux, use the same commands with `\` line continuations.

---

## 1. Prerequisites

| Needed | Check |
| ------ | ----- |
| Docker Desktop running | `docker info` |
| **Memory: 16 GB RAM or more** for the Docker VM / server | BGE-M3 is loaded by the retrieval and processing workers (~2 GB each), plus up to 2 GB per parser sandbox while a file is parsed. 8 GB works only for light testing |
| Ollama installed and running | `ollama list` |
| Ollama model pulled | `ollama pull qwen3:4b-instruct` (once, needs internet) |
| `backend/.env` filled in | copy `backend/.env.example` and change every `change-me` |
| `backend/app/infra/docker/.env` filled in | copy `app/infra/docker/.env.example` |

> **Ollama GPU note.** If Ollama returns `prediction aborted, token repeat limit reached` (or garbage text), its GPU backend is broken on that machine (seen with Vulkan on an integrated GPU). Set `OLLAMA_NUM_GPU=0` in `backend/.env` to run the model on CPU.

---

## 2. Start the infrastructure

```powershell
cd backend\app\infra\docker
docker network create contextapi-network   # once; "already exists" is fine
docker compose -f docker-compose.yml --env-file .env up -d
```

Starts Postgres, Redis, RabbitMQ, MinIO, ClamAV and ChromaDB on `contextapi-network`.

**First time only:** create the MinIO buckets (`contextapi-quarantine`, `contextapi-documents`, `contextapi-parsed`) at http://localhost:9001, or run `python dev.py` once, which creates them.

---

## 3. Build the images

```powershell
cd backend
docker build -t contextapi/backend:latest .
docker compose -f app\infra\docker\parsing\docker-compose.sandbox.yml build   # parser sandbox image
```

The parser sandbox image contains LibreOffice (old Office / OpenDocument files) and Tesseract OCR (English + Tamil). After rebuilding it, running sandboxes are replaced automatically on their next job.

---

## 4. Embedding models (offline)

`model-init` checks the `contextapi-app_hf-models` volume for **BAAI/bge-m3** and **BAAI/bge-reranker-base**. Anything already in the volume is used as is; only missing models are downloaded.

For an air-gapped server, fill the volume from a machine that already has the models in its Hugging Face cache (`~/.cache/huggingface/hub`). Symlinks must be resolved first: on Windows they are not visible inside containers.

```powershell
# 1. Resolve the symlinks into a plain folder (on the machine that has the models)
python -c "import shutil,os,pathlib; h=pathlib.Path(os.path.expanduser('~/.cache/huggingface/hub')); [shutil.copytree(h/m/s, pathlib.Path('hf-seed')/m/s, dirs_exist_ok=True) for m in ('models--BAAI--bge-m3','models--BAAI--bge-reranker-base') for s in ('refs','snapshots')]"

# 2. Copy that folder into the Docker volume
docker volume create contextapi-app_hf-models
docker run --rm -v "${PWD}\hf-seed:/src:ro" -v contextapi-app_hf-models:/dst alpine sh -c "mkdir -p /dst/hub && cp -r /src/. /dst/hub/ && chown -R 10001:10001 /dst"
```

---

## 5. Start the application

```powershell
cd backend\app\infra\docker
$env:DOCKER_GID = "0"     # Docker Desktop. On Linux: (getent group docker | cut -d: -f3)
docker compose -p contextapi-app -f docker-compose.app.yml --env-file ..\..\..\.env up -d
```

| Service | Role |
| ------- | ---- |
| `migrate` | `alembic upgrade head`, then exits |
| `model-init` | checks the models are in the volume, then exits |
| `sandbox-init` | gives the shared parser-sandbox folder to the app user, then idles (restarts with Docker so the chown re-runs after a Docker Desktop restart) |
| `api` | FastAPI on **http://localhost:8000** |
| `worker-default` | ingestion + emails (queues `celery,email`) |
| `worker-retrieval` | retrieval + LLM generation (queue `retrieval`) |
| `worker-processing` | chunking + embedding (queue `processing`), one document at a time, `PROCESSING_CPU_THREADS` (default 4) CPU threads, so uploads never slow retrieval |
| `beat` | scheduled jobs: fails stuck retrieval requests; every 5 min re-queues ingestion/indexing work left behind by a worker that died |

Check it is healthy:

```powershell
docker compose -p contextapi-app -f docker-compose.app.yml --env-file ..\..\..\.env ps -a
# migrate / model-init: Exited (0). Everything else: Up.
docker logs contextapi-app-worker-retrieval-1 --tail 5    # "... retrieval@... ready."
```

Always pass `--env-file ..\..\..\.env` to `docker compose` commands for this file, including `ps` and `logs`. Without it you get "variable is not set" warnings.

---

## 6. Test in Swagger

Open **http://localhost:8000/docs**.

### 6.1 Register and verify

1. `POST /auth/register`
   ```json
   { "email": "you@example.com", "username": "tester", "password": "Strong#Pass123", "confirm_password": "Strong#Pass123" }
   ```
2. Get the OTP. It is emailed. With no internet, read it from Redis instead:
   ```powershell
   docker exec contextapi-redis redis-cli GET "email_verify:you@example.com"
   ```
   (Add `-a <REDIS_PASSWORD>` if Redis has a password.)
3. `POST /auth/verify-email` → `{ "email": "you@example.com", "otp": "123456" }`

### 6.2 Log in

Click **Authorize** (top right). Enter your email in **username**, your password, and click *Authorize*. Swagger now sends the token with every call and keeps it after a page reload. Tokens last 15 minutes: when calls return 401, click Authorize again (Logout, then log in).

### 6.3 Create a project

`POST /projects/` (the example body is ready to use; change the name):
```json
{ "name": "My Docs", "description": "Documents to ask questions about", "status": "active" }
```
Copy the `project_id`. Retrieval only searches **active** projects. To activate an existing one: `PUT /projects/{project_id}` with only `{ "status": "active" }`.

### 6.4 Upload a document

`POST /upload/` with `project_id` and one or more files (up to 10 per request). Supported:

| Kind | Extensions |
| ---- | ---------- |
| PDF | `.pdf`: text PDFs, scanned / image-only PDFs and "Print to PDF" output (OCR), edited PDFs, PDFs with copy/print restrictions. Only password-protected PDFs are refused |
| Office | `.docx` `.pptx` `.xlsx`, older `.doc` `.ppt` `.xls`, `.rtf`, OpenDocument `.odt` `.ods` `.odp` |
| Images (OCR) | `.png` `.jpg` `.jpeg` `.bmp` `.tif` `.tiff` `.webp` |
| Web / text | `.html` `.htm` `.txt` `.md` `.rst` `.log` `.csv` `.tsv` (any encoding: UTF-8, UTF-16, Windows-1252) |
| Data / config | `.json` `.yaml` `.yml` `.xml` `.sql` `.ini` `.cfg` `.conf` `.properties` `.toml` |
| Source code | `.py` `.js` `.jsx` `.ts` `.tsx` `.java` `.kt` `.go` `.rs` `.c` `.h` `.cpp` `.hpp` `.cs` `.php` `.rb` `.swift` `.scala` `.sh` `.lua` `.r` `.dart` `.vb` |

Macros, ActiveX controls and embedded objects inside Office files are ignored (never run); only the text is used. Files with an embedded executable are refused.

Indexing takes a few seconds for a small file. OCR and large documents take longer: embedding runs on the CPU at roughly 1–2 s per chunk, so a 100-page document can take several minutes.

Check it with `GET /upload/documents`. Look at `indexing_status`:

| `indexing_status` | Meaning |
| ----------------- | ------- |
| `INGESTING` / `INDEXING` | still working, check again shortly |
| `READY` | searchable |
| `REJECTED` | failed a security/format check; `status_reason` says why |
| `FAILED` | an error after all retries; `status_reason` says why |

Common reasons: `DUPLICATE_FILE` (the same file is already in the project), `PDF_ENCRYPTED` (remove the password and upload again), `PARSER_VALIDATION_FAILED` (no readable text found, e.g. a blank scan).

### 6.5 Ask a question

`POST /api/v1/retrieval/requests`:
```json
{ "instruction": "What is ContextAPI?", "project_id": "PROJ000001", "profile": "DEEP", "top_k": 5 }
```
Copy the `request_id`.

| `profile` | What runs |
| --------- | --------- |
| `FAST` | retrieval only, no LLM |
| `STANDARD` (default) | retrieval + reranker, no LLM answer |
| `DEEP` | retrieval + reranker + **Ollama answer** (offline) |
| `COLLABORATIVE` | as DEEP, plus external LLM fallback only if Tier C API keys are set |

### 6.6 Read the answer

`GET /api/v1/retrieval/requests/{request_id}/answer` waits up to `wait_seconds` (default 30) and returns:

* `answer`: the answer with `[N]` citations
* `cited_sources`: the documents behind each `[N]`
* `top_results`: the best matching chunks, with a snippet
* `model_tier`: `"B"` = local Ollama
* `done`: `false` means it is still running. Execute again.

A DEEP request takes about 15–30 s with the model on CPU. The full detail (plan, evidence, sufficiency) is still at `GET /api/v1/retrieval/requests/{request_id}`.

> Type ids in path fields **without quotes**: `req_1a2b3c4d5e6f7a8b`, not `"req_1a2b3c4d5e6f7a8b"`.

---

## 7. Troubleshooting

| Symptom | Fix |
| ------- | --- |
| `generated_answer.warnings`: `token repeat limit reached` | Set `OLLAMA_NUM_GPU=0` in `.env`, then recreate the workers (see below) |
| `generated_answer.error_code`: `MODEL_UNAVAILABLE`, `Cannot reach Ollama` | Ollama is not running on the host, or the model is not pulled |
| Ingestion log: `Permission denied: /tmp/contextapi/parser-sandbox/...` | `sandbox-init` is not running (it re-chowns the folder after a Docker Desktop restart). Run `up -d` again |
| Ingestion log: cannot connect to Docker | `DOCKER_GID` is wrong (Docker Desktop: `0`) |
| Answers are slow (CPU-only Ollama) | Prompt reading (~60 tokens/s) dominates. Lower `GENERATION_CONTEXT_TOKENS` (default 1500) or `OLLAMA_NUM_PREDICT` (default 1024; answers stream, so a longer limit costs no waiting before the first words); `ollama ps` should show the model loaded with `UNTIL 24 hours from now` |
| `answer: null` with a warning | Read the warning: no matching text, or the project has no active documents. A question asked right after an upload waits up to `RETRIEVAL_INDEXING_WAIT_SECONDS` for indexing first |
| `PROJECT_NOT_ACTIVE` | `PUT /projects/{id}` with `{"status":"active"}` |
| 401 on every call | The token has expired (15 min). Log in again |
| A document stays `INGESTING`/`INDEXING` for a long time | Large files and OCR take minutes. A run left behind by a crashed worker is re-queued by `beat` within 5–30 min |
| API or workers restart by themselves | Out of memory. Give Docker more RAM (16 GB+) |

After changing `.env` or the code:

```powershell
cd backend
docker build -t contextapi/backend:latest .
cd app\infra\docker
docker compose -p contextapi-app -f docker-compose.app.yml --env-file ..\..\..\.env up -d --force-recreate api worker-default worker-retrieval worker-processing beat
```

Stop everything:

```powershell
docker compose -p contextapi-app -f docker-compose.app.yml --env-file ..\..\..\.env down
docker compose -f docker-compose.yml --env-file .env down
```

---

## 8. Running the tests

```powershell
cd backend
docker run --rm --env-file .env -v "${PWD}\tests:/app/tests:ro" contextapi/backend:latest python -m pytest tests -q --ignore=tests/integration
```

---

## 9. Known gaps

* `GET /upload/uploads` keeps showing `QUEUED`: the upload job's status is never updated after ingestion. Use `indexing_status` in `GET /upload/documents` instead.
* The parser sandbox containers run as root.
