from fastapi import FastAPI
import app.core.models
from app.core.logging import configure_logging
from app.core.database import Base, engine
from app.auth.router import router as auth_router
from app.project.router import router as project_router
from app.target_application.router import router as target_application_router
from app.knowledge.uploads.router import router as upload_router
from app.core.cors import configure_cors
from app.retrieval.router import router as retrieval_router


API_DESCRIPTION = """
Upload documents to a project, then ask questions about them. Answers come from
the local LLM (Ollama) and cite the documents they used.

### Quick start
1. **Log in:** click **Authorize** (top right), enter your email as *username* and your password.
   New user? Use `POST /auth/register` first, then `POST /auth/verify-email` with the OTP.
2. **Project:** `POST /projects/` with `"status": "active"`. Copy the `project_id`.
3. **Upload:** `POST /upload/` with the `project_id` and your file(s). Indexing takes a few seconds per file.
4. **Ask:** `POST /api/v1/retrieval/requests` with your question, the `project_id` and `"profile": "DEEP"`. Copy the `request_id`.
5. **Answer:** `GET /api/v1/retrieval/requests/{request_id}/answer`. It waits until the answer is ready.

Type ids in path fields without quotes, e.g. `PROJ000001`, not `"PROJ000001"`.
"""

OPENAPI_TAGS = [
    {"name": "Authentication", "description": "Register, verify email, log in."},
    {"name": "Projects", "description": "A project groups the documents you search. It must be `active` to be searched."},
    {"name": "Knowledge Upload", "description": "Upload documents into a project."},
    {"name": "Retrieval", "description": "Ask a question and read the answer."},
    {"name": "Target Applications", "description": "APIs to analyse (for the upcoming API discovery features)."},
]

configure_logging()
app = FastAPI(
    title="ContextAPI",
    version="1.0.0",
    description=API_DESCRIPTION,
    openapi_tags=OPENAPI_TAGS,
    swagger_ui_parameters={
        "persistAuthorization": True,       # stay logged in after a page reload
        "displayRequestDuration": True,
        "defaultModelsExpandDepth": -1,     # hide the Schemas section
        "docExpansion": "list",
        "tryItOutEnabled": True,            # no extra "Try it out" click
        "filter": True,
    },
)

configure_cors(app)
app.include_router(auth_router)
app.include_router(project_router)
app.include_router(target_application_router)
app.include_router(upload_router)
app.include_router(retrieval_router)