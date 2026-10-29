from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings


def configure_cors(app):
    # The web app normally reaches the API through its /backend proxy (Vite in
    # development, nginx in production), which is same-origin and needs no
    # CORS. These origins are only for a frontend calling the API directly.
    origins = [
        origin.strip().rstrip("/")
        for origin in settings.CORS_ORIGINS.split(",")
        if origin.strip()
    ]
    if not origins:
        return

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
