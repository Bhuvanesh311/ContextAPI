"""
Registers which retrieval capabilities actually exist.

SEMANTIC    - ChromaDB + bge-m3 (vector similarity)
LEXICAL     - Postgres full-text search on document_chunks.search_vector
HYBRID      - SEMANTIC + LEXICAL fused with Reciprocal Rank Fusion
STRUCTURED  - Postgres chunk_metadata exact-match queries (EXACT intent)

Imported once from router.py, so this runs at app startup.
"""

from app.core.enums import RetrievalRequirementType
from app.retrieval.planning.capabilities import registry, CapabilityDescriptor

_DONE = False


def register_capabilities() -> None:
    global _DONE
    if _DONE:
        return

    registry.register(
        CapabilityDescriptor(
            capability_id="cap_semantic",
            capability_type=RetrievalRequirementType.SEMANTIC,
        )
    )
    registry.register(
        CapabilityDescriptor(
            capability_id="cap_lexical",
            capability_type=RetrievalRequirementType.LEXICAL,
        )
    )
    registry.register(
        CapabilityDescriptor(
            capability_id="cap_hybrid",
            capability_type=RetrievalRequirementType.HYBRID,
        )
    )
    registry.register(
        CapabilityDescriptor(
            capability_id="cap_structured",
            capability_type=RetrievalRequirementType.EXACT,
        )
    )

    # Models are preloaded by the retrieval Celery worker (app/retrieval/tasks.py),
    # not here: the API process no longer runs retrieval.
    _DONE = True