"""
Schemas for the L8-L11 augmentation pipeline.

    L9  (context_assembly) -> AssembledContext      (OptimizedContextPackage)
    L10 (prompt_builder)   -> BuiltPrompt           (GroundedModelRequest)
    L11 G5 (generator)     -> GenerationResult
    L11 G6/G7 (validator)  -> GeneratedAnswer
    L11 G9 (service)       -> GeneratedAnswer with final status (GeneratedResult),
                              stored in RetrievalRequest.generated_answer
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class GenerationStatus(str, Enum):
    SUCCESS = "SUCCESS"                            # grounded answer from sufficient evidence
    PARTIAL = "PARTIAL"                            # answer exists, but evidence or grounding is incomplete
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"  # evidence cannot answer the question (no LLM call, or model abstained)
    FAILED = "FAILED"                              # model unavailable, budget/time exhausted, or unsafe output
    CANCELLED = "CANCELLED"                        # request cancelled before generation
    SKIPPED = "SKIPPED"                            # profile does not generate (FAST / STANDARD)


class ContextItem(BaseModel):
    rank: int
    evidence_id: str
    content: str
    document_id: str
    document_name: Optional[str] = None
    chunk_id: str
    score: float
    tokens: int


class AssembledContext(BaseModel):
    items: List[ContextItem] = Field(default_factory=list)
    total_tokens: int = 0
    budget_tokens: int = 0
    truncated: bool = False
    items_dropped: int = 0          # dropped by integrity / dedup / budget
    conflict_notes: List[str] = Field(default_factory=list)


class BuiltPrompt(BaseModel):
    system_prompt: str
    user_prompt: str
    intent: str
    estimated_tokens: int
    memory_count: int = 0


class GenerationResult(BaseModel):
    text: str = ""
    tokens_used: int = 0
    cost_used: float = 0.0
    tier: str = ""
    model: str = ""
    llm_calls: int = 0
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    # True when the model stopped at the output-token limit (answer is cut short).
    truncated: bool = False


class CitationRef(BaseModel):
    citation_number: int
    evidence_id: str
    chunk_id: str
    document_id: Optional[str] = None
    document_name: Optional[str] = None


class GeneratedAnswer(BaseModel):
    status: GenerationStatus = GenerationStatus.FAILED
    answer: str = ""
    output_mode: str = "answer"                    # "answer" (user) | "structured" (agent / planner / workflow)
    citations: List[CitationRef] = Field(default_factory=list)
    grounding_score: float = 0.0                   # supported claims / factual claims
    supported_claims: int = 0
    factual_claims: int = 0
    invalid_citations: List[int] = Field(default_factory=list)
    abstained: bool = False                        # model said the context cannot answer
    evidence_verdict: Optional[str] = None         # L07 verdict the answer was built on
    tokens_used: int = 0
    cost_used: float = 0.0
    tier: str = ""
    model: str = ""
    llm_calls: int = 0
    latency_ms: int = 0
    warnings: List[str] = Field(default_factory=list)
    error_code: Optional[str] = None
    skipped: bool = False
    skip_reason: Optional[str] = None
    repair_attempted: bool = False
