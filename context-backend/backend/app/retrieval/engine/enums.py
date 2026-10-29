from enum import Enum

class ExecutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    ESCALATE = "ESCALATE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    SKIPPED = "SKIPPED"

class OperatorType(str, Enum):
    SEMANTIC = "SEMANTIC"
    LEXICAL = "LEXICAL"
    HYBRID = "HYBRID"
    STRUCTURED = "STRUCTURED"
    GRAPH = "GRAPH"
    MULTI_HOP = "MULTI_HOP"
    AGENTIC = "AGENTIC"

class FusionStrategy(str, Enum):
    RRF = "RRF"
    SCORE_BASED = "SCORE_BASED"
    DETERMINISTIC = "DETERMINISTIC"
    PRIORITY = "PRIORITY"