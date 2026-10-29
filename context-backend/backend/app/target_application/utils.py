from sqlalchemy import text
from sqlalchemy.orm import Session


def get_next_target_sequence(db: Session) -> str:
    result = db.execute(
        text("SELECT nextval('target_url_sequence')")
    )
    return result.scalar_one()

def generate_target_application_id(sequence: int)-> str:
    return f"URL{sequence:06d}"