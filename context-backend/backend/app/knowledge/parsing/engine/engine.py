from __future__ import annotations

import logging
import traceback
from pathlib import Path

from app.knowledge.parsing.engine.base import BaseParser
from app.knowledge.parsing.engine.router import ParserRouter
from app.knowledge.parsing.schemas import (
    ParsingRequest,
    ParserResult,
)
from app.knowledge.parsing.exceptions import (
    ParserException,
    UnsupportedFileTypeError,
)
from app.knowledge.parsing.validation.output_validator import (
    OutputValidator,
)


logger = logging.getLogger(__name__)


class ParsingEngine:


    def __init__(
        self,
        router: ParserRouter | None = None,
        validator: OutputValidator | None = None,
    ) -> None:
        self.router = router or ParserRouter()
        self.validator = validator or OutputValidator()

    def execute(
        self,
        file_path: Path,
        request: ParsingRequest,
    ) -> ParserResult:

        parser: BaseParser | None = None

        try:
           
            # 1. SELECT PARSER
           

            parser = self.router.get_parser(request)

            logger.info(
                "Parser selected",
                extra={
                    "document_id": request.document_id,
                    "parser": parser.parser_name,
                    "extension": request.extension,
                },
            )

           
            # 2. EXECUTE PARSER
           

            document = parser.parse(
                file_path=file_path,
                request=request,
            )

            if document is None:
                raise ParserException(
                    "Parser returned an empty document."
                )

           
            # 3. VALIDATE OUTPUT
           

            self.validator.validate(document)

           
            # 4. SUCCESS
           

            logger.info(
                "Parsing completed successfully",
                extra={
                    "document_id": request.document_id,
                    "parser": parser.parser_name,
                    "file": file_path.name,
                },
            )

            return ParserResult(
                success=True,
                parser_name=parser.parser_name,
                document=document,
                error_message=None,
            )

      
        # UNSUPPORTED FILE TYPE
      

        except UnsupportedFileTypeError as error:

            parser_name = (
                parser.parser_name
                if parser is not None
                else "unknown"
            )

            logger.warning(
                "Unsupported file type",
                extra={
                    "document_id": request.document_id,
                    "extension": request.extension,
                    "parser": parser_name,
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
            )

            return ParserResult(
                success=False,
                parser_name=parser_name,
                document=None,
                error_message=(
                    f"{type(error).__name__}: {error}"
                ),
            )

      
        # EXPECTED PARSER FAILURE
      

        except ParserException as error:

            parser_name = (
                parser.parser_name
                if parser is not None
                else "unknown"
            )

            error_type = type(error).__name__
            error_message = str(error)

            logger.warning(
                "Parser execution failed",
                extra={
                    "document_id": request.document_id,
                    "parser": parser_name,
                    "error_type": error_type,
                    "error": error_message,
                },
            )

       

            return ParserResult(
                success=False,
                parser_name=parser_name,
                document=None,
                error_message=(
                    f"{error_type}: {error_message}"
                ),
            )

      
        # UNEXPECTED FAILURE
      

        except Exception as error:

            parser_name = (
                parser.parser_name
                if parser is not None
                else "unknown"
            )

            error_type = type(error).__name__
            error_message = str(error)
            stack_trace = traceback.format_exc()

            logger.exception(
                "Unexpected parsing engine failure",
                extra={
                    "document_id": request.document_id,
                    "parser": parser_name,
                    "error_type": error_type,
                    "error": error_message,
                },
            )

            return ParserResult(
                success=False,
                parser_name=parser_name,
                document=None,
                error_message=(
                    f"Unexpected parser error: "
                    f"{error_type}: {error_message}"
                ),
            )