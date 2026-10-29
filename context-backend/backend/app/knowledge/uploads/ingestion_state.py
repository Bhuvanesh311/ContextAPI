from app.core.enums import (
    IngestionStage,
    IngestionRunStatus,
)


STAGE_ORDER = [
    IngestionStage.UPLOAD_RECEIVED,
    IngestionStage.QUARANTINE_STORAGE,
    IngestionStage.PRE_SECURITY_VALIDATION,
    IngestionStage.FORMAT_IDENTIFICATION,
    IngestionStage.FORMAT_VALIDATION,
    IngestionStage.PARSER_SELECTION,
    IngestionStage.SANDBOXED_PARSING,
    IngestionStage.POST_PARSE_VALIDATION,
    IngestionStage.AI_RAG_SECURITY_VALIDATION,
    IngestionStage.PERMANENT_STORAGE,
    IngestionStage.CLEANUP,
    IngestionStage.COMPLETED,
]


TERMINAL_STAGES = {
    IngestionStage.COMPLETED,
}


def get_next_stage(
    current_stage: IngestionStage,
) -> IngestionStage | None:

    try:
        index = STAGE_ORDER.index(current_stage)
    except ValueError:
        raise ValueError(
            f"Unknown ingestion stage: {current_stage}"
        )

    if index >= len(STAGE_ORDER) - 1:
        return None

    return STAGE_ORDER[index + 1]


def is_terminal_stage(
    stage: IngestionStage,
) -> bool:
    return stage in TERMINAL_STAGES


def is_valid_stage_transition(
    current_stage: IngestionStage,
    next_stage: IngestionStage,
) -> bool:

    expected_next = get_next_stage(current_stage)

    return expected_next == next_stage


def validate_stage_transition(
    current_stage: IngestionStage,
    next_stage: IngestionStage,
) -> None:

    if not is_valid_stage_transition(
        current_stage,
        next_stage,
    ):
        raise ValueError(
            f"Invalid ingestion stage transition: "
            f"{current_stage} -> {next_stage}"
        )


def can_start_processing(
    status: IngestionRunStatus,
) -> bool:

    return status in {
        IngestionRunStatus.PENDING,
        IngestionRunStatus.RETRYING,
    }