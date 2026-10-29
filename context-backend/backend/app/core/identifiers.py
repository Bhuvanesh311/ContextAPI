import uuid


def generate_offline_id(prefix: str) -> str:
    """Generate a unique identifier without touching the database.

    Used for in-memory / offline pydantic models (evidence sets, traces,
    etc.) where a DB sequence isn't available or appropriate. Format:
    "<PREFIX>-<12 hex chars>", e.g. "EVA-SET-9f3a2c1e0b7d".
    """
    return f"{prefix}-{uuid.uuid4().hex[:12]}"