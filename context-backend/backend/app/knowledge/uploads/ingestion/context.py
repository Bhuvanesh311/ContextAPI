from dataclasses import dataclass
from sqlalchemy.orm import Session
from app.knowledge.uploads.models import IngestionRun, Document, DocumentVersion

@dataclass
class IngestionContext:
    db: Session
    run: IngestionRun
    document: Document
    document_version: DocumentVersion
