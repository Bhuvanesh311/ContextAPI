from __future__ import annotations

import configparser
import tomllib

import javaproperties

from app.knowledge.security.stage_3.context import ValidationContext
from app.knowledge.security.stage_3.exceptions import (
    FormatSecurityError,
)


def validate(
    context: ValidationContext,
) -> None:
    """
    Validate configuration files before sandbox parsing.

    Supported:
        - ini
        - cfg
        - conf
        - properties
        - toml
    """

    extension = context.extension.lower()

    if extension in {
        ".ini",
        ".cfg",
    }:
        _validate_ini(context)
        
    elif extension == ".conf":
        _validate_conf(context)

    elif extension == ".properties":
        _validate_properties(context)

    elif extension == ".toml":
        _validate_toml(context)

    else:
        raise FormatSecurityError(
            f"Unsupported configuration format '{extension}'.",
            phase="format_validation",
            check="configuration_validation",
            code="UNSUPPORTED_FORMAT",
        )

    context.security_validated = True


def _validate_ini(
    context: ValidationContext,
) -> None:

    parser = configparser.ConfigParser()

    try:

        parser.read(
            context.file_path,
            encoding="utf-8",
        )

    except Exception as exc:

        raise FormatSecurityError(
            "Invalid configuration file.",
            phase="format_validation",
            check="ini",
            code="INVALID_CONFIGURATION",
        ) from exc


def _validate_properties(
    context: ValidationContext,
) -> None:

    try:

        with context.file_path.open(
            "rb",
        ) as file:

            javaproperties.load(file)

    except Exception as exc:

        raise FormatSecurityError(
            "Invalid Java properties file.",
            phase="format_validation",
            check="properties",
            code="INVALID_PROPERTIES",
        ) from exc


def _validate_toml(
    context: ValidationContext,
) -> None:

    try:

        with context.file_path.open(
            "rb",
        ) as file:

            tomllib.load(file)

    except Exception as exc:

        raise FormatSecurityError(
            "Invalid TOML document.",
            phase="format_validation",
            check="toml",
            code="INVALID_TOML",
        ) from exc


def _validate_conf(
    context: ValidationContext,
) -> None:

    try:

        with context.file_path.open(
            "r",
            encoding="utf-8-sig",
        ) as file:

            for _ in file:
                pass

    except Exception as exc:

        raise FormatSecurityError(
            "Invalid CONF configuration.",
            phase="format_validation",
            check="conf",
            code="INVALID_CONFIGURATION",
        ) from exc