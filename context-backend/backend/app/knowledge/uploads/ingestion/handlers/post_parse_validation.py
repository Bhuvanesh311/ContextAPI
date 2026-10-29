import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.core.enums import IngestionStage
from app.infra.storage import storage_service
from app.knowledge.parsing.schemas import NormalizedDocument
from app.knowledge.parsing.enums import ParserFormat
from app.knowledge.post_security.context import PostSecurityContext
from app.knowledge.post_security.stage_4 import pipeline as post_security_stage_4

from app.knowledge.uploads.ingestion.context import IngestionContext
from app.knowledge.uploads.ingestion.result import IngestionStageResult

logger = logging.getLogger(__name__)

class PostParseValidationHandler:
    def execute(self, context: IngestionContext) -> IngestionStageResult:
        run = context.run
        document = context.document
        document_version = context.document_version

        parsed_bucket = document_version.parsed_bucket
        parsed_object_key = document_version.parsed_object_key

        if not parsed_bucket:
            return IngestionStageResult(success=False, error_message="INVALID_ARTIFACT: Parsed artifact bucket is missing.")

        if not parsed_object_key:
            return IngestionStageResult(success=False, error_message="INVALID_ARTIFACT: Parsed artifact object key is missing.")

        logger.info(
            "Starting post-parse validation",
            extra={
                "ingestion_run_id": run.ingestion_run_id,
                "document_id": document.document_id,
                "document_version_id": document_version.document_version_id,
                "parsed_bucket": parsed_bucket,
                "parsed_object_key": parsed_object_key,
            },
        )

        # 1. VERIFY PARSED ARTIFACT EXISTS
        if not storage_service.exists(bucket=parsed_bucket, object_key=parsed_object_key):
            return IngestionStageResult(success=False, error_message="ARTIFACT_NOT_FOUND: Parsed artifact does not exist.")

        # 2. READ ACTUAL CANONICAL PARSED ARTIFACT
        response = None
        try:
            response = storage_service.download(bucket=parsed_bucket, object_key=parsed_object_key)
            raw_bytes = response.read()
        except Exception as exc:
            return IngestionStageResult(success=False, error_message="INVALID_ARTIFACT: Unable to read parsed artifact.")
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass
                try:
                    response.release_conn()
                except Exception:
                    pass

        if not raw_bytes:
            return IngestionStageResult(success=False, error_message="INVALID_ARTIFACT: Parsed artifact is empty.")

        # 3. DECODE JSON
        try:
            raw_json = json.loads(raw_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return IngestionStageResult(success=False, error_message="INVALID_ARTIFACT: Parsed artifact is not valid UTF-8 JSON.")

        if not isinstance(raw_json, dict):
            return IngestionStageResult(success=False, error_message="INVALID_ARTIFACT: Parsed artifact root must be a JSON object.")

        # 4. VALIDATE CANONICAL PARSER SCHEMA
        try:
            parsed_document = NormalizedDocument.model_validate(raw_json)
        except Exception as exc:
            return IngestionStageResult(success=False, error_message="INVALID_ARTIFACT: Parsed artifact does not match the canonical parser schema.")

        # 5. IDENTITY / PROVENANCE VALIDATION
        if parsed_document.document_id != document.document_id:
            return IngestionStageResult(success=False, error_message="INVALID_ARTIFACT: Parsed document_id does not match the ingestion document.")

        if parsed_document.file_name != document_version.file_name:
            return IngestionStageResult(success=False, error_message="INVALID_ARTIFACT: Parsed file_name does not match the document version.")

        # 6. FORMAT CONSISTENCY
        checkpoint = dict(run.checkpoint_data or {})
        parser_format_value = checkpoint.get("parser_format")
        if not parser_format_value:
            return IngestionStageResult(success=False, error_message="INVALID_ARTIFACT: No parser format recorded in checkpoint.")
            
        expected_format = ParserFormat(parser_format_value)

        if parsed_document.source_format != expected_format:
            return IngestionStageResult(success=False, error_message="INVALID_ARTIFACT: Parsed source format does not match the validated document format.")

        # 7. CONTENT / STATISTICS CONSISTENCY
        actual_character_count = len(parsed_document.content)
        actual_word_count = len(parsed_document.content.split())

        if parsed_document.character_count != actual_character_count:
            return IngestionStageResult(success=False, error_message="INVALID_ARTIFACT: Parsed character_count is inconsistent with parsed content.")

        if parsed_document.word_count != actual_word_count:
            return IngestionStageResult(success=False, error_message="INVALID_ARTIFACT: Parsed word_count is inconsistent with parsed content.")

        if not parsed_document.content.strip():
            return IngestionStageResult(success=False, error_message="INVALID_ARTIFACT: Parsed artifact contains no usable content.")

        # 8. BUILD POST-SECURITY CONTEXT
        references = parsed_document.metadata.get("references", [])
        if references is None:
            references = []

        if not isinstance(references, list):
            return IngestionStageResult(success=False, error_message="INVALID_ARTIFACT: Parsed references must be a list.")

        if not all(isinstance(reference, str) for reference in references):
            return IngestionStageResult(success=False, error_message="INVALID_ARTIFACT: Parsed references must contain strings only.")

        post_sec_context = PostSecurityContext(
            document=parsed_document.content,
            metadata=parsed_document.metadata,
            references=references,
            expected_document_id=document.document_id,
            expected_project_id=document.project_id,
            expected_document_version_id=document_version.document_version_id,
            expected_file_name=document_version.file_name,
            expected_source_sha256=document_version.sha256_hash,
            expected_source_format=parsed_document.source_format.value,
            expected_mime_type=document_version.mime_type,
            expected_parser_name=checkpoint.get("parser_name"),
        )

        post_sec_context.add_attribute("document_id", document.document_id)
        post_sec_context.add_attribute("project_id", document.project_id)
        post_sec_context.add_attribute("document_version_id", document_version.document_version_id)
        post_sec_context.add_attribute("parsed_bucket", parsed_bucket)
        post_sec_context.add_attribute("parsed_object_key", parsed_object_key)
        post_sec_context.add_attribute("source_object_key", document_version.quarantine_object_key)
        post_sec_context.add_attribute("source_sha256", document_version.sha256_hash)
        post_sec_context.add_attribute("parser_name", checkpoint.get("parser_name"))
        post_sec_context.add_attribute("source_format", parsed_document.source_format.value)
        post_sec_context.add_attribute("page_count", parsed_document.page_count)
        post_sec_context.add_attribute("character_count", parsed_document.character_count)
        post_sec_context.add_attribute("word_count", parsed_document.word_count)

        # 9. EXECUTE STAGE 4
        post_sec_context = post_security_stage_4.execute(post_sec_context)

        findings = [
            {
                "code": finding.code,
                "title": finding.title,
                "message": finding.message,
                "severity": finding.severity.value,
                "phase": finding.phase,
                "metadata": finding.metadata,
            }
            for finding in post_sec_context.findings
        ]

        # 10. REJECT INVALID ARTIFACT
        if not post_sec_context.is_valid:
            logger.warning(
                "Post-parse validation rejected artifact",
                extra={
                    "ingestion_run_id": run.ingestion_run_id,
                    "document_id": document.document_id,
                    "finding_count": len(findings),
                },
            )
            return IngestionStageResult(success=False, error_message="INVALID_ARTIFACT: Parsed artifact failed Stage 4 validation.")

        # 11. SAVE VALIDATION CHECKPOINT
        checkpoint.update({
            "stage": IngestionStage.POST_PARSE_VALIDATION.value,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "validated": True,
            "stage_4": {
                "status": "PASSED",
                "contract_version": "1.0",
                "risk_score": post_sec_context.risk_score,
                "finding_count": len(findings),
            },
            "document_id": document.document_id,
            "document_version_id": document_version.document_version_id,
            "parsed_bucket": parsed_bucket,
            "parsed_object_key": parsed_object_key,
            "source_format": parsed_document.source_format.value,
            "character_count": parsed_document.character_count,
            "word_count": parsed_document.word_count,
            "page_count": parsed_document.page_count,
            "finding_count": len(findings),
            "findings": findings,
            "normalized_document": post_sec_context.normalized_document,
        })

        logger.info(
            "Post-parse validation completed successfully",
            extra={
                "ingestion_run_id": run.ingestion_run_id,
                "document_id": document.document_id,
                "document_version_id": document_version.document_version_id,
                "finding_count": len(findings),
            },
        )

        return IngestionStageResult(
            success=True,
            checkpoint_data=checkpoint
        )
