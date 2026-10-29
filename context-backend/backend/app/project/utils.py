from sqlalchemy import text
from sqlalchemy.orm import Session


def get_next_project_sequence(db: Session) -> str:
    result = db.execute(
        text("SELECT nextval('project_sequence')")
    )
    return result.scalar_one()


def generate_project_id(sequence: int)-> str:
    return f"PROJ{sequence:06d}"