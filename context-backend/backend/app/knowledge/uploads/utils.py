
from sqlalchemy import text
from sqlalchemy.orm import Session
from pathlib import Path
import hashlib

def get_next_upload_sequence(db:Session)->int :
    result =db.execute(
        text(" SELECT nextval('upload_sequence')")
    )
    return result.scalar_one()


def generate_upload_id(sequence: int)-> str:
    return f"UPL{sequence:06d}"



def get_next_document_sequence(db:Session)->int :
    result =db.execute(
        text(" SELECT nextval('document_sequence')")
    )
    return result.scalar_one()


def generate_document_id(sequence: int)-> str:
    return f"DOC{sequence:06d}"


def get_next_document_version_sequence(db: Session) -> int:
    result = db.execute(
        text("SELECT nextval('document_version_sequence')")
    )
    return result.scalar_one()


def generate_document_version_id(sequence: int) -> str:
    return f"DOC-VER{sequence:06d}"


def get_next_ingestion_run_sequence(db: Session) -> int:
    result = db.execute(
        text("SELECT nextval('ingestion_run_sequence')")
    )
    return result.scalar_one()


def generate_ingestion_run_id(sequence: int) -> str:
    return f"ING{sequence:06d}"


def get_next_knowledge_processing_run_sequence(db: Session) -> int:
    result = db.execute(
        text("SELECT nextval('knowledge_processing_run_sequence')")
    )
    return result.scalar_one()


def generate_knowledge_processing_run_id(sequence: int) -> str:
    return f"KPR{sequence:06d}"


def get_next_document_chunk_sequence(db: Session) -> int:
    result = db.execute(
        text("SELECT nextval('document_chunk_sequence')")
    )
    return result.scalar_one()


def generate_document_chunk_id(sequence: int) -> str:
    return f"CHK{sequence:06d}"


def get_next_chunk_embedding_sequence(db: Session) -> int:
    result = db.execute(
        text("SELECT nextval('chunk_embedding_sequence')")
    )
    return result.scalar_one()


def generate_chunk_embedding_id(sequence: int) -> str:
    return f"EMBD{sequence:06d}"





def generate_storage_filename( document_id: str,extension: str,) -> str:
    extension = extension.lower().lstrip(".")

    return f"{document_id}.{extension}"

def normalize_filename(filename: str,) -> str:

    return filename.strip()



def get_file_extension(filename: str,) -> str:
    
    return Path(filename).suffix.lower()



def calculate_checksum(data: bytes,) -> str:
    
    return hashlib.sha256(data).hexdigest()