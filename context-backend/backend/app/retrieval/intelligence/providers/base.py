from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

class AbstractModelProvider(ABC):
    """
    Base abstraction for SLM/LLM capabilities.
    """
    
    @abstractmethod
    def generate_structured(
        self,
        prompt: str,
        schema: Dict[str, Any],
        timeout: int = 60,
        system: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a structured JSON response matching the given JSON schema.
        `system` carries trusted instructions as the model's system message.
        """
        pass
