import math
from collections import Counter

from app.knowledge.security.stage_1.constants import (
    ENTROPY_HIGH,
    ENTROPY_NORMAL,
    ENTROPY_SAMPLE_SIZE,
    ENTROPY_SUSPICIOUS,
    HIGH_ENTROPY_THRESHOLD,
    SUSPICIOUS_ENTROPY_THRESHOLD,
)
from app.knowledge.security.stage_1.context import ValidationContext
from app.knowledge.security.stage_1.exceptions import EntropyAnalysisError


def analyze_entropy(context: ValidationContext) -> None:

    try:
        with context.file_path.open("rb") as file:
            sample = file.read(ENTROPY_SAMPLE_SIZE)

    except OSError as exc:
        raise EntropyAnalysisError(
            f"Unable to read '{context.original_filename}' "
            f"for entropy analysis.",
            phase="security",
            check="entropy_analysis",
            code="ENTROPY_READ_FAILED",
        ) from exc

    if not sample:
        raise EntropyAnalysisError(
            f"No content available for entropy analysis in "
            f"'{context.original_filename}'.",
            phase="security",
            check="entropy_analysis",
            code="ENTROPY_SAMPLE_EMPTY",
        )

    byte_counts = Counter(sample)
    total_bytes = len(sample)

    entropy = -sum(
        (count / total_bytes)
        * math.log2(count / total_bytes)
        for count in byte_counts.values()
    )

    context.entropy = entropy

    if entropy >= SUSPICIOUS_ENTROPY_THRESHOLD:
        context.entropy_classification = ENTROPY_SUSPICIOUS

    elif entropy >= HIGH_ENTROPY_THRESHOLD:
        context.entropy_classification = ENTROPY_HIGH

    else:
        context.entropy_classification = ENTROPY_NORMAL