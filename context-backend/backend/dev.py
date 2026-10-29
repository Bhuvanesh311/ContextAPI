"""
ContextAPI - one-command local dev launcher.

Run from the `backend` folder with the virtual environment active:

    python dev.py

Optional flags:
    --skip-install      do not run pip install (even if requirements changed)
    --skip-ollama       do not check / download the Ollama model
    --rebuild-sandbox   force rebuild of the parser sandbox image

What it does (in order):
    1.  Loads .env
    2.  Checks Python / venv / Docker
    3.  Creates the Docker network
    4.  Installs Python requirements (only when requirements.txt changed)
    5.  Starts Docker infrastructure (Postgres, Redis, RabbitMQ, MinIO, ClamAV, ChromaDB, Neo4j)
    6.  Waits until the services accept connections
    7.  Creates the MinIO buckets
    8.  Runs Alembic migrations
    9.  Checks Ollama and downloads the model if missing
    10. Fixes entrypoint.sh line endings and builds / tests the sandbox image
    11. Starts FastAPI and Celery
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


# ============================================================
# CONFIG
# ============================================================

BACKEND_DIR = Path(__file__).resolve().parent

ENV_FILE = BACKEND_DIR / ".env"
REQUIREMENTS_FILE = BACKEND_DIR / "requirements.txt"
GITIGNORE_FILE = BACKEND_DIR / ".gitignore"

DOCKER_DIR = BACKEND_DIR / "app" / "infra" / "docker"
DOCKER_COMPOSE_FILE = DOCKER_DIR / "docker-compose.yml"
DOCKER_ENV_FILE = DOCKER_DIR / ".env"

SANDBOX_DIR = DOCKER_DIR / "parsing"
SANDBOX_DOCKERFILE = SANDBOX_DIR / "dockerfile"
SANDBOX_ENTRYPOINT = SANDBOX_DIR / "entrypoint.sh"

CACHE_DIR = BACKEND_DIR / ".dev_cache"
REQUIREMENTS_HASH_FILE = CACHE_DIR / "requirements.sha256"

DOCKER_NETWORK = "contextapi-network"
SANDBOX_IMAGE = "contextapi/parser-sandbox:latest"
SANDBOX_BANNER = "ContextAPI Parser Sandbox Started"

API_HOST = "127.0.0.1"
API_PORT = 8000

CELERY_APP = "app.infra.celery.app.celery_app"
# One worker per queue group: a 60 s retrieval must never delay OTP / login
# emails or ingestion. Same split as docker-compose.app.yml.
CELERY_WORKERS = {
    "default": "celery,email",
    "retrieval": "retrieval",
    "processing": "processing",
}
PYTHON_VERSION_FILE = BACKEND_DIR / ".python-version"

RERANKER_MODEL = "BAAI/bge-reranker-base"

# Docker commands must NOT see the values of backend/.env.
# We copy the clean environment before loading .env.
CLEAN_ENV = os.environ.copy()


# ============================================================
# TERMINAL HELPERS
# ============================================================

def header() -> None:
    print()
    print("=" * 60)
    print("                     CONTEXTAPI DEV")
    print("=" * 60)
    print()


def info(message: str) -> None:
    print(f"[ContextAPI] {message}")


def ok(message: str) -> None:
    print(f"[OK]       {message}")


def warn(message: str) -> None:
    print(f"[WARN]     {message}")


def fail(message: str) -> None:
    print(f"[ERROR]    {message}")
    sys.exit(1)


def run(
    command: list[str],
    *,
    check: bool = True,
    capture: bool = False,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    print()
    print("$", " ".join(str(part) for part in command))

    return subprocess.run(
        command,
        cwd=BACKEND_DIR,
        check=check,
        capture_output=capture,
        text=True,
        env=env,
    )


# ============================================================
# .ENV
# ============================================================

def load_env_file() -> None:
    info("Loading .env")

    if not ENV_FILE.exists():
        fail(f".env not found: {ENV_FILE}")

    with ENV_FILE.open("r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()

            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()

            if (
                len(value) >= 2
                and value[0] == value[-1]
                and value[0] in {"'", '"'}
            ):
                value = value[1:-1]

            # Real environment variables win over the file.
            os.environ.setdefault(key, value)

    ok(".env loaded")


# ============================================================
# PYTHON / DOCKER CHECKS
# ============================================================

def check_python() -> None:
    info("Checking Python")

    version = sys.version_info
    pinned = PYTHON_VERSION_FILE.read_text(encoding="utf-8").strip()
    current = f"{version.major}.{version.minor}"

    if current != pinned:
        warn(
            f"Project is pinned to Python {pinned} (.python-version, Dockerfile), "
            f"you are on {current}. Create the venv with Python {pinned}: "
            f"py -{pinned} -m venv .venv"
        )

    if sys.prefix == sys.base_prefix:
        warn("Virtual environment is not active. Activate .venv first.")

    ok(f"Python {version.major}.{version.minor}.{version.micro}")


def check_docker() -> None:
    info("Checking Docker")

    if shutil.which("docker") is None:
        fail("Docker was not found in PATH. Install Docker Desktop.")

    result = subprocess.run(
        ["docker", "info"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=CLEAN_ENV,
    )

    if result.returncode != 0:
        fail("Docker is not running. Start Docker Desktop and run again.")

    ok("Docker is running")


def ensure_docker_network() -> None:
    info(f"Checking Docker network: {DOCKER_NETWORK}")

    result = subprocess.run(
        ["docker", "network", "inspect", DOCKER_NETWORK],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=CLEAN_ENV,
    )

    if result.returncode == 0:
        ok(f"Network exists: {DOCKER_NETWORK}")
        return

    run(["docker", "network", "create", DOCKER_NETWORK], env=CLEAN_ENV)
    ok(f"Network created: {DOCKER_NETWORK}")


# ============================================================
# PYTHON REQUIREMENTS
# ============================================================

def file_hash(path: Path) -> str:
    sha = hashlib.sha256()

    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            sha.update(chunk)

    return sha.hexdigest()


def ensure_cache_ignored() -> None:
    """Keep .dev_cache/ out of git."""
    entry = ".dev_cache/"

    if GITIGNORE_FILE.exists():
        content = GITIGNORE_FILE.read_text(encoding="utf-8")

        if entry in content.splitlines():
            return

        GITIGNORE_FILE.write_text(
            content.rstrip("\n") + "\n" + entry + "\n",
            encoding="utf-8",
        )
    else:
        GITIGNORE_FILE.write_text(entry + "\n", encoding="utf-8")


def install_requirements(skip: bool) -> None:
    info("Checking Python requirements")

    if skip:
        warn("Skipped (--skip-install)")
        return

    if not REQUIREMENTS_FILE.exists():
        fail(f"requirements.txt not found: {REQUIREMENTS_FILE}")

    current = file_hash(REQUIREMENTS_FILE)
    stored = (
        REQUIREMENTS_HASH_FILE.read_text(encoding="utf-8").strip()
        if REQUIREMENTS_HASH_FILE.exists()
        else ""
    )

    if current == stored:
        ok("Python requirements are up to date")
        return

    info("requirements.txt changed (or first run). Installing...")

    run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-r",
            str(REQUIREMENTS_FILE),
        ]
    )

    CACHE_DIR.mkdir(exist_ok=True)
    REQUIREMENTS_HASH_FILE.write_text(current, encoding="utf-8")
    ensure_cache_ignored()

    ok("Python requirements installed")


# ============================================================
# INFRASTRUCTURE
# ============================================================

def start_infrastructure() -> None:
    info("Starting Docker infrastructure")

    if not DOCKER_COMPOSE_FILE.exists():
        fail(f"Compose file not found: {DOCKER_COMPOSE_FILE}")

    command = ["docker", "compose", "-f", str(DOCKER_COMPOSE_FILE)]

    if DOCKER_ENV_FILE.exists():
        command += ["--env-file", str(DOCKER_ENV_FILE)]

    # --remove-orphans drops containers of services no longer in compose (e.g. neo4j).
    command += ["up", "-d", "--remove-orphans"]

    run(command, env=CLEAN_ENV)
    ok("Infrastructure containers started")


def port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def wait_for_port(
    name: str,
    host: str,
    port: int,
    *,
    timeout: int,
    required: bool,
) -> None:
    info(f"Waiting for {name} ({host}:{port})")

    deadline = time.time() + timeout

    while time.time() < deadline:
        if port_open(host, port):
            ok(f"{name} is ready")
            return

        time.sleep(2)

    message = f"{name} did not open {host}:{port} within {timeout}s"

    if required:
        fail(message)

    warn(message + " (continuing)")


def split_endpoint(endpoint: str) -> tuple[str, int]:
    host, _, port = endpoint.rpartition(":")
    return host or "localhost", int(port)


def wait_for_services() -> None:
    env = os.environ

    minio_host, minio_port = split_endpoint(
        env.get("MINIO_ENDPOINT", "localhost:9000")
    )

    services = [
        ("Postgres", env.get("POSTGRES_HOST", "localhost"), int(env.get("POSTGRES_PORT", "5433")), 60, True),
        ("Redis", env.get("REDIS_HOST", "localhost"), int(env.get("REDIS_PORT", "6380")), 60, True),
        ("RabbitMQ", env.get("RABBITMQ_HOST", "localhost"), int(env.get("RABBITMQ_PORT", "5673")), 90, True),
        ("MinIO", minio_host, minio_port, 60, True),
        ("ChromaDB", env.get("CHROMADB_HOST", "localhost"), int(env.get("CHROMADB_PORT", "8001")), 60, True),
        # ClamAV loads its virus database first. It can be slow.
        ("ClamAV", env.get("CLAMAV_HOST", "localhost"), int(env.get("CLAMAV_PORT", "3310")), 240, False),
    ]

    for name, host, port, timeout, required in services:
        wait_for_port(name, host, port, timeout=timeout, required=required)


# ============================================================
# MINIO BUCKETS
# ============================================================

BUCKET_SCRIPT = """
from app.core.config import settings
from app.infra.storage.client import minio_client

names = (
    settings.MINIO_QUARANTINE_BUCKET,
    settings.MINIO_DOCUMENT_BUCKET,
    settings.MINIO_PARSED_BUCKET,
)

for name in names:
    if minio_client.bucket_exists(name):
        print("exists  :", name)
    else:
        minio_client.make_bucket(name)
        print("created :", name)
"""


def ensure_minio_buckets() -> None:
    info("Checking MinIO buckets")

    last_error = ""

    for attempt in range(1, 6):
        result = subprocess.run(
            [sys.executable, "-c", BUCKET_SCRIPT],
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                ok(line)
            return

        last_error = (result.stderr or result.stdout).strip()
        info(f"MinIO not ready yet (attempt {attempt}/5)")
        time.sleep(3)

    print(last_error)
    fail(
        "Could not create MinIO buckets. Check MINIO_ACCESS_KEY / "
        "MINIO_SECRET_KEY in .env match the MinIO container."
    )


# ============================================================
# DATABASE MIGRATIONS
# ============================================================

def run_migrations() -> None:
    info("Running database migrations")

    run([sys.executable, "-m", "alembic", "upgrade", "head"])

    ok("Database is up to date")


# ============================================================
# OLLAMA
# ============================================================

def ollama_models(base_url: str) -> list[str] | None:
    try:
        with urllib.request.urlopen(
            base_url.rstrip("/") + "/api/tags",
            timeout=3,
        ) as response:
            data = json.load(response)
    except (urllib.error.URLError, OSError, ValueError):
        return None

    return [item.get("name", "") for item in data.get("models", [])]


def ensure_ollama(skip: bool) -> None:
    info("Checking Ollama")

    if skip:
        warn("Skipped (--skip-ollama)")
        return

    env = os.environ

    if env.get("POST_SECURITY_AI_PROVIDER", "ollama").lower() != "ollama":
        ok("Post-security AI provider is not Ollama. Nothing to check")
        return

    base_url = env.get("POST_SECURITY_AI_BASE_URL", "http://localhost:11434")
    model = env.get("POST_SECURITY_AI_MODEL", "qwen3:4b-instruct")

    models = ollama_models(base_url)

    if models is None:
        warn(
            f"Ollama is not reachable at {base_url}. "
            f"Open the Ollama app. Files flagged by the security scan "
            f"cannot be AI-checked until it runs."
        )
        return

    installed = {name for name in models} | {
        name.removesuffix(":latest") for name in models
    }

    if model in installed:
        ok(f"Ollama model ready: {model}")
        return

    if shutil.which("ollama") is None:
        warn(f"Model '{model}' is missing and the ollama command was not found.")
        return

    info(f"Downloading Ollama model: {model} (about 2.5 GB, first time only)")

    result = run(["ollama", "pull", model], check=False)

    if result.returncode == 0:
        ok(f"Ollama model downloaded: {model}")
    else:
        warn(f"Could not download {model}. Run 'ollama pull {model}' manually.")


# ============================================================
# RERANKER MODEL
# ============================================================

_RERANKER_CHECK_SCRIPT = """
import os, sys
# Remove offline flag so we can check and download freely.
os.environ.pop("HF_HUB_OFFLINE", None)
os.environ.pop("TRANSFORMERS_OFFLINE", None)
model_name = sys.argv[1]
from huggingface_hub import snapshot_download
# Try local cache first (no network); if incomplete, download the full snapshot.
try:
    snapshot_download(model_name, local_files_only=True)
    print("cached")
    sys.exit(0)
except Exception:
    pass
# Full download — includes config, tokeniser and model weights.
snapshot_download(model_name)
print("downloaded")
"""


def ensure_reranker_model() -> None:
    info(f"Checking reranker model: {RERANKER_MODEL}")

    result = subprocess.run(
        [sys.executable, "-c", _RERANKER_CHECK_SCRIPT, RERANKER_MODEL],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
    )

    output = (result.stdout or "").strip()

    if result.returncode == 0 and output in ("cached", "downloaded"):
        ok(f"Reranker model ready: {RERANKER_MODEL}")
        return

    warn(
        f"Could not download reranker model '{RERANKER_MODEL}'. "
        f"Reranking will be skipped until the model is available. "
        f"Run: python -c \"from sentence_transformers import CrossEncoder; "
        f"CrossEncoder('{RERANKER_MODEL}')\" (without HF_HUB_OFFLINE=1)."
    )
    if result.stderr:
        warn(result.stderr.strip().splitlines()[-1])


# ============================================================
# PARSER SANDBOX IMAGE
# ============================================================

def normalize_entrypoint_line_endings() -> bool:
    """
    Windows git checkouts turn LF into CRLF. A shell script with CRLF
    fails inside Linux containers (the container exits immediately).
    Returns True when the file had to be fixed.
    """
    if not SANDBOX_ENTRYPOINT.exists():
        fail(f"entrypoint.sh not found: {SANDBOX_ENTRYPOINT}")

    data = SANDBOX_ENTRYPOINT.read_bytes()

    if b"\r\n" not in data:
        return False

    SANDBOX_ENTRYPOINT.write_bytes(data.replace(b"\r\n", b"\n"))
    warn("entrypoint.sh had Windows line endings (CRLF). Converted to LF.")
    return True


def sandbox_image_exists() -> bool:
    result = subprocess.run(
        ["docker", "image", "inspect", SANDBOX_IMAGE],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=CLEAN_ENV,
    )

    return result.returncode == 0


def build_sandbox_image() -> None:
    info("Building parser sandbox image (first time can take 10-20 minutes)")

    if not SANDBOX_DOCKERFILE.exists():
        fail(f"Sandbox dockerfile not found: {SANDBOX_DOCKERFILE}")

    run(
        [
            "docker",
            "build",
            "-t",
            SANDBOX_IMAGE,
            "-f",
            str(SANDBOX_DOCKERFILE),
            ".",
        ],
        env=CLEAN_ENV,
    )

    ok("Sandbox image built")


def sandbox_image_works() -> bool:
    result = subprocess.run(
        ["docker", "run", "--rm", SANDBOX_IMAGE, "echo", "ok"],
        capture_output=True,
        text=True,
        env=CLEAN_ENV,
    )

    return result.returncode == 0 and SANDBOX_BANNER in result.stdout


def ensure_sandbox_image(force_rebuild: bool) -> None:
    info("Checking parser sandbox image")

    entrypoint_fixed = normalize_entrypoint_line_endings()

    if force_rebuild or entrypoint_fixed or not sandbox_image_exists():
        build_sandbox_image()

    info("Testing sandbox image")

    if sandbox_image_works():
        ok("Sandbox image works")
        return

    warn("Sandbox image failed the smoke test. Rebuilding once.")
    build_sandbox_image()

    if not sandbox_image_works():
        fail(
            "Sandbox image still fails. Run: "
            f"docker run --rm {SANDBOX_IMAGE} echo ok"
        )

    ok("Sandbox image works")


# ============================================================
# LOCAL APPLICATION PROCESSES
# ============================================================

def ensure_api_port_free() -> None:
    if port_open(API_HOST, API_PORT):
        fail(
            f"Port {API_PORT} is already in use. Stop the old Uvicorn "
            f"(and old Celery) terminals first, then run dev.py again."
        )


def start_fastapi() -> subprocess.Popen:
    info("Starting FastAPI")

    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--reload",
            "--host",
            API_HOST,
            "--port",
            str(API_PORT),
        ],
        cwd=BACKEND_DIR,
    )


def start_celery(name: str, queues: str) -> subprocess.Popen:
    info(f"Starting Celery worker '{name}' (queues: {queues})")

    command = [
        sys.executable,
        "-m",
        "celery",
        "-A",
        CELERY_APP,
        "worker",
        "--loglevel=info",
        "-n",
        f"{name}@%h",
        "-Q",
        queues,
    ]

    # Windows cannot use the default prefork pool. solo runs one task at a
    # time, so say so instead of showing the CPU count as concurrency.
    if os.name == "nt":
        command += ["--pool=solo", "--concurrency=1"]

    return subprocess.Popen(command, cwd=BACKEND_DIR)


def start_celery_beat() -> subprocess.Popen:
    info("Starting Celery beat (scheduled housekeeping)")
    CACHE_DIR.mkdir(exist_ok=True)
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "celery",
            "-A",
            CELERY_APP,
            "beat",
            "--loglevel=info",
            "-s",
            str(CACHE_DIR / "celerybeat-schedule"),
        ],
        cwd=BACKEND_DIR,
    )


def stop_process(process: subprocess.Popen | None, name: str) -> None:
    if process is None or process.poll() is not None:
        return

    info(f"Stopping {name}")

    if os.name == "nt":
        # Kill the whole tree (uvicorn --reload starts a child process).
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        process.terminate()

    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()

    ok(f"{name} stopped")


# ============================================================
# MAIN
# ============================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ContextAPI dev launcher")
    parser.add_argument("--skip-install", action="store_true")
    parser.add_argument("--skip-ollama", action="store_true")
    parser.add_argument("--rebuild-sandbox", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    header()

    fastapi_process = None
    celery_processes: dict[str, subprocess.Popen] = {}

    try:
        load_env_file()
        check_python()
        check_docker()
        ensure_docker_network()
        install_requirements(args.skip_install)

        start_infrastructure()
        wait_for_services()

        ensure_minio_buckets()
        run_migrations()

        ensure_ollama(args.skip_ollama)
        ensure_reranker_model()
        ensure_sandbox_image(args.rebuild_sandbox)

        ensure_api_port_free()

        fastapi_process = start_fastapi()
        for name, queues in CELERY_WORKERS.items():
            celery_processes[name] = start_celery(name, queues)
        celery_processes["beat"] = start_celery_beat()

        print()
        print("=" * 60)
        print("                CONTEXTAPI DEV READY")
        print("=" * 60)
        print()
        print(f"FastAPI : http://{API_HOST}:{API_PORT}")
        print(f"Docs    : http://{API_HOST}:{API_PORT}/docs")
        for name, queues in CELERY_WORKERS.items():
            print(f"Celery  : {name:<9} -> {queues}")
        print()
        print("Press Ctrl+C to stop FastAPI and Celery.")
        print("Docker infrastructure will keep running.")
        print()

        while True:
            if fastapi_process.poll() is not None:
                print("[ERROR]    FastAPI process exited.")
                break

            exited = [n for n, p in celery_processes.items() if p.poll() is not None]
            if exited:
                print(f"[ERROR]    Celery worker exited: {', '.join(exited)}")
                break

            time.sleep(1)

    except KeyboardInterrupt:
        print()
        info("Shutdown requested")

    except subprocess.CalledProcessError as exc:
        print()
        print(f"[ERROR]    Command failed with exit code {exc.returncode}")

    finally:
        print()
        info("Stopping local application processes")

        stop_process(fastapi_process, "FastAPI")
        for name, process in celery_processes.items():
            stop_process(process, f"Celery ({name})")

        print()
        print("Docker containers were left running.")
        print("To stop them: docker compose -f app/infra/docker/docker-compose.yml down")
        print()


if __name__ == "__main__":
    main()