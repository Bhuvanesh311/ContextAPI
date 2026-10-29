from __future__ import annotations

import logging
import shutil
from pathlib import Path


logger = logging.getLogger(__name__)


class Workspace:
  

    INPUT_DIR = "input"
    OUTPUT_DIR = "output"
    TEMP_DIR = "temp"
    LOGS_DIR = "logs"

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

        self.input = self.root / self.INPUT_DIR
        self.output = self.root / self.OUTPUT_DIR
        self.temp = self.root / self.TEMP_DIR
        self.logs = self.root / self.LOGS_DIR


    def create(self) -> None:


        logger.debug(
            "Creating sandbox workspace",
            extra={
                "workspace": str(self.root),
            },
        )

        self.root.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.input.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.output.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.temp.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.logs.mkdir(
            parents=True,
            exist_ok=True,
        )

    def cleanup(self) -> None:
     

        if not self.root.exists():
            return

        logger.debug(
            "Cleaning sandbox workspace",
            extra={
                "workspace": str(self.root),
            },
        )

        for directory in (
            self.input,
            self.output,
            self.temp,
            self.logs,
        ):
            if not directory.exists():
                directory.mkdir(
                    parents=True,
                    exist_ok=True,
                )
                continue

            for item in directory.iterdir():
                try:
                    if item.is_dir():
                        shutil.rmtree(item)

                    else:
                        item.unlink()

                except Exception:
                    logger.exception(
                        "Failed to remove workspace item",
                        extra={
                            "workspace": str(self.root),
                            "item": str(item),
                        },
                    )

                    raise

    def destroy(self) -> None:
       
        if not self.root.exists():
            return

        logger.info(
            "Destroying sandbox workspace",
            extra={
                "workspace": str(self.root),
            },
        )

        shutil.rmtree(
            self.root,
        )


    def exists(self) -> bool:

        return self.root.exists()

    def is_empty(self) -> bool:
    

        if not self.root.exists():
            return True

        for directory in (
            self.input,
            self.output,
            self.temp,
            self.logs,
        ):
            if directory.exists() and any(
                directory.iterdir()
            ):
                return False

        return True


    def resolve(self) -> Path:
     

        return self.root.resolve()

    def input_file(self, filename: str) -> Path:
      

        return self.input / filename

    def output_file(self, filename: str) -> Path:
  
        return self.output / filename

    def temp_file(self, filename: str) -> Path:
     

        return self.temp / filename

    def log_file(self, filename: str) -> Path:
       

        return self.logs / filename
