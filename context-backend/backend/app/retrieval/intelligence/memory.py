
from app.core.enums import MemoryRequirement

def analyze_memory(query: str) -> MemoryRequirement:
    if not query:
        return MemoryRequirement.NONE
        
    lower = query.lower()
    
    if "previously" in lower or "earlier in this chat" in lower or "what did we say" in lower:
        return MemoryRequirement.SESSION
    elif "always" in lower or "my preferences" in lower or "remember" in lower:
        return MemoryRequirement.LONG_TERM
    elif "status of my task" in lower or "workflow" in lower:
        return MemoryRequirement.WORKFLOW
        
    return MemoryRequirement.NONE