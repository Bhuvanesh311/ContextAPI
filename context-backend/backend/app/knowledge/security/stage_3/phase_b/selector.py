from __future__ import annotations

from app.core.enums import FileCategory
from app.knowledge.security.stage_3.context import ValidationContext
from app.knowledge.security.stage_3.exceptions import (
    FormatSecurityError,
)

from app.knowledge.security.stage_3.phase_b.validators import pdf
from app.knowledge.security.stage_3.phase_b.validators import office
from app.knowledge.security.stage_3.phase_b.validators import structured
from app.knowledge.security.stage_3.phase_b.validators import config
from app.knowledge.security.stage_3.phase_b.validators import text
from app.knowledge.security.stage_3.phase_b.validators import source
from app.knowledge.security.stage_3.phase_b.validators import image
from app.knowledge.security.stage_3.phase_b.validators import legacy_office
VALIDATOR_REGISTRY = {
    FileCategory.PDF.value: ("pdf_validator", pdf.validate),
    FileCategory.OFFICE.value: ("office_validator", office.validate),
    FileCategory.STRUCTURED.value: ("structured_validator", structured.validate),
    FileCategory.CONFIGURATION.value: ("configuration_validator", config.validate),
    FileCategory.TEXT.value: ("text_validator", text.validate),
    FileCategory.SOURCE_CODE.value: ("source_validator", source.validate),
    FileCategory.IMAGE.value: ("image_validator", image.validate),
    FileCategory.LEGACY_OFFICE.value: ("legacy_office_validator", legacy_office.validate),
}


def select_validator(
    context: ValidationContext,
):
    """
    Phase B

    Select the appropriate format-specific validator
    based on the document category.
    """

    validator = VALIDATOR_REGISTRY.get(
        context.format_family,
    )

    if validator is None:
        raise FormatSecurityError(
            f"No validator registered for "
            f"'{context.format_family}'.",
            phase="validator_selection",
            check="validator_selection",
            code="VALIDATOR_NOT_FOUND",
        )

    validator_name, validator_function = validator

    context.validator_name = validator_name
    context.validator_selected = True

    return validator_function