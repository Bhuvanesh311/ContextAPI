"""
L8 Memory schemas.

RelevantMemoryPackage is the output of L8 and is passed into L9 (prompt_builder)
alongside the AssembledContext from context_assembly.
"""

from enum import Enum
from typing import Any, Dict, List
from pydantic import BaseModel, Field


class MemorySourceType(str, Enum):
    SESSION   = "session"    # current correlation_id conversation turns
    LONG_TERM = "long_term"  # cross-session user facts
    AGENT     = "agent"      # agent / workflow state (source_type-gated)
    EVIDENCE  = "evidence"   # shared evidence chunks from prior retrieval rounds


class MemoryItem(BaseModel):
    item_id: str
    source_type: MemorySourceType
    content: str
    relevance_score: float = 0.0   # raw term-coverage (0..1)
    priority_score: float = 0.0    # combined: relevance + source-priority + recency
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RelevantMemoryPackage(BaseModel):
    session_items:   List[MemoryItem] = Field(default_factory=list)
    long_term_items: List[MemoryItem] = Field(default_factory=list)
    agent_items:     List[MemoryItem] = Field(default_factory=list)
    evidence_items:  List[MemoryItem] = Field(default_factory=list)
    total_items: int = 0
    total_tokens: int = 0

    def all_items(self) -> List[MemoryItem]:
        """All items sorted by combined priority_score descending."""
        return sorted(
            self.session_items + self.long_term_items
            + self.agent_items + self.evidence_items,
            key=lambda x: x.priority_score,
            reverse=True,
        )
