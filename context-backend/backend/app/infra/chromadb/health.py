from chromadb.errors import ChromaError

from app.infra.chromadb.client import chroma_client
from app.infra.chromadb.exceptions import ChromaConnectionError


def check_chromadb_health() -> bool:
    """
    Verify that the ChromaDB server is reachable.
    """

    try:
        chroma_client.heartbeat()
        return True

    except ChromaError as exc:
        raise ChromaConnectionError(
            "Unable to connect to the ChromaDB server."
        ) from exc

    except Exception as exc:
        raise ChromaConnectionError(
            "Unexpected error while connecting to ChromaDB."
        ) from exc