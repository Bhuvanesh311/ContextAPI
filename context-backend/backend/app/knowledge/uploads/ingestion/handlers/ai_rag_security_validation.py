import json
import logging
from datetime import datetime, timezone

from app.core.config import settings
from app.core.enums import IngestionStage, DocumentStatus
from app.infra.storage import storage_service
from app.knowledge.parsing.schemas import NormalizedDocument
from app.knowledge.post_security.context import PostSecurityContext
from app.knowledge.post_security.enums import SecurityDecision
from app.knowledge.post_security.tasks import PostSecurityTask
from app.knowledge.post_security.stage_6.pipeline import Stage6Pipeline

from app.knowledge.uploads.ingestion.context import IngestionContext
from app.knowledge.uploads.ingestion.result import IngestionStageResult
from app.knowledge.uploads.ingestion_service import save_ingestion_checkpoint

logger = logging.getLogger(__name__)

class AiRagSecurityValidationHandler:
    def execute(self, context: IngestionContext) -> IngestionStageResult:
        run = context.run
        document = context.document
        document_version = context.document_version
        
        logger.info(
            "Starting AI/RAG security validation",
            extra={
                "ingestion_run_id": run.ingestion_run_id,
                "document_id": document.document_id,
                "document_version_id": document_version.document_version_id,
            },
        )
        
        parsed_bucket = document_version.parsed_bucket
        parsed_object_key = document_version.parsed_object_key
        
        if not parsed_bucket or not parsed_object_key:
            return IngestionStageResult(success=False, error_message="ARTIFACT_NOT_FOUND: Document version does not have a parsed bucket/key.")
            
        if not storage_service.exists(bucket=parsed_bucket, object_key=parsed_object_key):
            return IngestionStageResult(success=False, error_message="ARTIFACT_NOT_FOUND: Parsed artifact does not exist.")
            
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
                    logger.warning("Failed to close parsed artifact storage response")
                try:
                    response.release_conn()
                except Exception:
                    logger.warning("Failed to release parsed artifact storage connection")
                    
        try:
            parsed_payload = json.loads(raw_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return IngestionStageResult(success=False, error_message="INVALID_ARTIFACT: Parsed artifact contains invalid JSON.")
            
        try:
            parsed_document = NormalizedDocument.model_validate(parsed_payload)
        except Exception as exc:
            return IngestionStageResult(success=False, error_message="INVALID_ARTIFACT: Parsed artifact does not satisfy schema.")
            
        if parsed_document.document_id != document.document_id:
            return IngestionStageResult(success=False, error_message="INVALID_ARTIFACT: Parsed document ID does not match.")
            
        metadata = parsed_document.metadata if isinstance(parsed_document.metadata, dict) else {}
        references = metadata.get("references", [])
        if references is None:
            references = []
        if not isinstance(references, list) or not all(isinstance(r, str) for r in references):
            return IngestionStageResult(success=False, error_message="INVALID_ARTIFACT: Parsed references must be a list of strings.")
            
        post_sec_context = PostSecurityContext(
            document=parsed_document.content,
            metadata=metadata,
            references=references,
        )
        
        post_sec_context.add_attribute("document_id", document.document_id)
        post_sec_context.add_attribute("project_id", document.project_id)
        post_sec_context.add_attribute("document_version_id", document_version.document_version_id)
        post_sec_context.add_attribute("parsed_bucket", parsed_bucket)
        post_sec_context.add_attribute("parsed_object_key", parsed_object_key)
        post_sec_context.add_attribute("source_object_key", document_version.quarantine_object_key)
        post_sec_context.add_attribute("source_sha256", document_version.sha256_hash)
        post_sec_context.add_attribute("source_format", parsed_document.source_format.value)
        post_sec_context.add_attribute("page_count", parsed_document.page_count)
        post_sec_context.add_attribute("character_count", parsed_document.character_count)
        post_sec_context.add_attribute("word_count", parsed_document.word_count)
        
        task = PostSecurityTask()
        result = task.execute(post_sec_context)
        stage_5_decision = result.decision
        findings = list(result.context.findings)
        
        serialized_findings = []
        for finding in findings:
            serialized_findings.append({
                "code": finding.code,
                "title": finding.title,
                "message": finding.message,
                "severity": finding.severity.value if hasattr(finding.severity, "value") else str(finding.severity),
                "phase": finding.phase,
                "metadata": finding.metadata or {},
            })
            
        checkpoint = dict(run.checkpoint_data or {})
        
        if stage_5_decision in {SecurityDecision.BLOCK, SecurityDecision.REVIEW}:
            stage_5_decision_value = stage_5_decision.value if hasattr(stage_5_decision, "value") else str(stage_5_decision)
            security_status = "blocked" if stage_5_decision == SecurityDecision.BLOCK else "review_required"
            
            checkpoint.update({
                "stage": IngestionStage.AI_RAG_SECURITY_VALIDATION.value,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "validated": True,
                "document_id": document.document_id,
                "document_version_id": document_version.document_version_id,
                "parsed_bucket": parsed_bucket,
                "parsed_object_key": parsed_object_key,
                "stage_5_decision": stage_5_decision_value,
                "decision": stage_5_decision_value,
                "confidence": result.confidence,
                "reason": result.reason,
                "risk_score": result.context.risk_score,
                "finding_count": len(serialized_findings),
                "findings": serialized_findings,
                "security_status": security_status,
                "ai_verification": {
                    "executed": False,
                    "reason": "AI verification was not allowed to override the deterministic Stage 5 security decision.",
                },
            })
            
            # Since orchestrator intercepts the failure and we want to preserve DB state side-effect:
            run.checkpoint_data = checkpoint
            document.status = DocumentStatus.REJECTED
            document.updated_at = datetime.now(timezone.utc)
            context.db.commit()
            
            error_prefix = "SECURITY_REJECTED: " if stage_5_decision == SecurityDecision.BLOCK else "SECURITY_REVIEW_REQUIRED: "
            # Name what was found so the uploader can see why the file was refused.
            found = "; ".join(
                f"{f['title']} ({f['code']}): \"{f['metadata']['matched_text']}\""
                if f["metadata"].get("matched_text") else f"{f['title']} ({f['code']})"
                for f in serialized_findings[:3]
            )
            detail = f" Found: {found}." if found else ""
            return IngestionStageResult(success=False, error_message=error_prefix + str(result.reason) + detail)
            
        try:
            stage_6_pipeline = Stage6Pipeline()
            stage_6_result = stage_6_pipeline.execute(findings)
        except Exception as exc:
            logger.exception("Stage 6 AI security verification failed")
            stage_5_decision_value = stage_5_decision.value if hasattr(stage_5_decision, "value") else str(stage_5_decision)
            
            checkpoint.update({
                "stage": IngestionStage.AI_RAG_SECURITY_VALIDATION.value,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "validated": False,
                "document_id": document.document_id,
                "document_version_id": document_version.document_version_id,
                "parsed_bucket": parsed_bucket,
                "parsed_object_key": parsed_object_key,
                "stage_5_decision": stage_5_decision_value,
                "decision": "REVIEW",
                "confidence": 0.0,
                "reason": "Stage 6 AI verification failed.",
                "risk_score": result.context.risk_score,
                "finding_count": len(serialized_findings),
                "findings": serialized_findings,
                "security_status": "review_required",
                "ai_verification": {
                    "executed": True,
                    "failed": True,
                    "error": str(exc),
                },
            })
            run.checkpoint_data = checkpoint
            document.status = DocumentStatus.REJECTED
            document.updated_at = datetime.now(timezone.utc)
            context.db.commit()
            return IngestionStageResult(success=False, error_message="SECURITY_REVIEW_REQUIRED: Stage 6 AI verification failed.")
            
        decision = stage_6_result.decision
        decision_value = decision.value if hasattr(decision, "value") else str(decision)
        stage_5_decision_value = stage_5_decision.value if hasattr(stage_5_decision, "value") else str(stage_5_decision)
        
        checkpoint.update({
            "stage": IngestionStage.AI_RAG_SECURITY_VALIDATION.value,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "validated": True,
            "document_id": document.document_id,
            "document_version_id": document_version.document_version_id,
            "parsed_bucket": parsed_bucket,
            "parsed_object_key": parsed_object_key,
            "stage_5_decision": stage_5_decision_value,
            "decision": decision_value,
            "confidence": stage_6_result.confidence,
            "reason": stage_6_result.reason,
            "risk_score": result.context.risk_score,
            "finding_count": len(serialized_findings),
            "findings": serialized_findings,
            "security_status": None,
            "ai_verification": {
                "executed": True,
                "provider": "ollama",
                "model": settings.POST_SECURITY_AI_MODEL if hasattr(settings, "POST_SECURITY_AI_MODEL") else None,
                "confidence": stage_6_result.confidence,
                "reason": stage_6_result.reason,
            },
        })
        
        if decision == SecurityDecision.BLOCK:
            checkpoint["security_status"] = "blocked"
            run.checkpoint_data = checkpoint
            document.status = DocumentStatus.REJECTED
            document.updated_at = datetime.now(timezone.utc)
            context.db.commit()
            return IngestionStageResult(success=False, error_message="SECURITY_REJECTED: " + stage_6_result.reason)
            
        if decision == SecurityDecision.REVIEW:
            checkpoint["security_status"] = "review_required"
            run.checkpoint_data = checkpoint
            document.status = DocumentStatus.REJECTED
            document.updated_at = datetime.now(timezone.utc)
            context.db.commit()
            return IngestionStageResult(success=False, error_message="SECURITY_REVIEW_REQUIRED: " + stage_6_result.reason)
            
        if decision != SecurityDecision.ALLOW:
            checkpoint["security_status"] = "blocked"
            run.checkpoint_data = checkpoint
            document.status = DocumentStatus.REJECTED
            document.updated_at = datetime.now(timezone.utc)
            context.db.commit()
            return IngestionStageResult(success=False, error_message="SECURITY_REJECTED: Unknown post-security decision.")
            
        checkpoint["security_status"] = "approved"
        
        # Validated successfully
        from app.core.enums import DocumentVersionStatus
        document_version.status = DocumentVersionStatus.VALIDATED
        document.updated_at = datetime.now(timezone.utc)
        document_version.updated_at = datetime.now(timezone.utc)
        context.db.commit() # Wait, the orchestrator commits at the end of the stage. But original code committed here too. Let's do it for consistency.
        
        logger.info("AI/RAG security validation completed successfully")
        
        return IngestionStageResult(
            success=True,
            checkpoint_data=checkpoint
        )
