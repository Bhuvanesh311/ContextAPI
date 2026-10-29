from abc import ABC, abstractmethod
from pathlib import Path
from app.knowledge.parsing.schemas import NormalizedDocument,ParsingRequest

class BaseParser(ABC):
    parser_name: str = "base_parser"
    supported_extensions: tuple[str,...] = ()

    @abstractmethod
    def parse(
        self,
        file_path: Path,
        request: ParsingRequest,
    ) ->NormalizedDocument:
    
        raise NotImplementedError

