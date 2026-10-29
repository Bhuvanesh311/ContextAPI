from app.core.enums import KnowledgeProcessingStage


STAGE_ORDER: tuple[KnowledgeProcessingStage, ...] = (
    KnowledgeProcessingStage.INITIALIZATION,
    KnowledgeProcessingStage.SOURCE_VALIDATION,
    KnowledgeProcessingStage.CHUNKING,
    KnowledgeProcessingStage.CHUNK_VALIDATION,
    KnowledgeProcessingStage.EMBEDDING,
    KnowledgeProcessingStage.VECTOR_INDEXING,
    KnowledgeProcessingStage.INDEX_VALIDATION,
    KnowledgeProcessingStage.COMPLETED,
)


TERMINAL_STAGES: frozenset[KnowledgeProcessingStage] = frozenset(
    {
        KnowledgeProcessingStage.COMPLETED,
    }
)


def is_terminal_stage(stage: KnowledgeProcessingStage) -> bool:
    return stage in TERMINAL_STAGES


def get_next_stage(
    stage: KnowledgeProcessingStage,
) -> KnowledgeProcessingStage | None:
    try:
        current_index = STAGE_ORDER.index(stage)
    except ValueError as exc:
        raise ValueError(f"Unknown knowledge processing stage: {stage}") from exc

    if current_index >= len(STAGE_ORDER) - 1:
        return None

    return STAGE_ORDER[current_index + 1]