from app.knowledge.parsing.schemas import NormalizedDocument
from app.knowledge.parsing.exceptions import OutputValidationError


class OutputValidator:

    def validate(
        self,
        document: NormalizedDocument,
    ) -> None:

      self.validate_required_fields(document)

      self.validate_document_id(document)

      self.validate_format(document)

      self.validate_metadata(document)

      self.validate_content(document)


    def validate_required_fields(
        self,
        document: NormalizedDocument,
    ) -> None:

        if not document.document_id:
            raise OutputValidationError(
                "Missing document_id."
            )

        if not document.file_name:
            raise OutputValidationError(
                "Missing file_name."
            )

        if document.source_format is None:
            raise OutputValidationError(
                "Missing source_format."
            )

        if document.content is None:
            raise OutputValidationError(
                "Missing content."
            )

        if document.metadata is None:
            raise OutputValidationError(
                "Missing metadata."
            )

    def validate_document_id(
        self,
        document: NormalizedDocument,
    ) -> None:

        if len(document.document_id.strip()) == 0:
            raise OutputValidationError(
                "Document ID cannot be empty."
            )

        if len(document.document_id) > 100:
            raise OutputValidationError(
                "Document ID exceeds maximum length."
            )

        
    def validate_format(
        self,
        document: NormalizedDocument,
    ) -> None:

        if not document.source_format.value:
            raise OutputValidationError(
                "Invalid document format."
            )


    def validate_metadata(
        self,
        document: NormalizedDocument,
    ) -> None:

        if not isinstance(
            document.metadata,
            dict
        ):
            raise OutputValidationError(
                "Metadata must be dictionary."
            )


    def validate_content(
        self,
        document: NormalizedDocument,
    ) -> None:

        if len(document.content.strip()) == 0:
            raise OutputValidationError(
                "Content cannot be empty."
            )