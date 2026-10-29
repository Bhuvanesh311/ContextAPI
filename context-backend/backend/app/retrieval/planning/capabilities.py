
from typing import List, Optional
from app.core.enums import RetrievalRequirementType
from app.retrieval.planning.schemas import CapabilityDescriptor

class CapabilityRegistry:
    def __init__(self):
        self._capabilities: List[CapabilityDescriptor] = []

    def register(self, descriptor: CapabilityDescriptor) -> None:
        self._capabilities.append(descriptor)

    def get_eligible_capabilities(self, req_type: RetrievalRequirementType) -> List[CapabilityDescriptor]:
        return [c for c in self._capabilities if c.capability_type == req_type and c.is_available]

    def clear(self) -> None:
        self._capabilities.clear()

# A global registry instance for L04 planning
registry = CapabilityRegistry()
