from app.knowledge.security.stage_1.context import ValidationContext
from app.knowledge.security.stage_1.exceptions import SignatureValidationError


_ZIP_SIGNATURES = (
    (0, b"PK\x03\x04"),
    (0, b"PK\x05\x06"),
    (0, b"PK\x07\x08"),
)

# OLE2 compound file (.doc / .xls / .ppt)
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

# Known File Signatures

FILE_SIGNATURES: dict[
    str,
    tuple[tuple[int, bytes], ...],
] = {
    ".pdf": (
        (0, b"%PDF-"),
    ),

    ".docx": (
        (0, b"PK\x03\x04"),
        (0, b"PK\x05\x06"),
        (0, b"PK\x07\x08"),
    ),

    ".pptx": _ZIP_SIGNATURES,
    ".xlsx": _ZIP_SIGNATURES,
    ".odt": _ZIP_SIGNATURES,
    ".ods": _ZIP_SIGNATURES,
    ".odp": _ZIP_SIGNATURES,
    # A ".doc" may really be RTF (Word opens both).
    ".doc": ((0, _OLE_MAGIC), (0, b"{\\rtf")),
    ".xls": ((0, _OLE_MAGIC),),
    ".ppt": ((0, _OLE_MAGIC),),
    ".rtf": ((0, b"{\\rtf"),),
    ".png": ((0, b"\x89PNG\r\n\x1a\n"),),
    ".jpg": ((0, b"\xff\xd8\xff"),),
    ".jpeg": ((0, b"\xff\xd8\xff"),),
    ".bmp": ((0, b"BM"),),
    ".tif": ((0, b"II*\x00"), (0, b"MM\x00*")),
    ".tiff": ((0, b"II*\x00"), (0, b"MM\x00*")),
    ".webp": ((8, b"WEBP"),),

    ".zip": (
        (0, b"PK\x03\x04"),
        (0, b"PK\x05\x06"),
        (0, b"PK\x07\x08"),
    ),

    ".tar": (
        (257, b"ustar"),
    ),
}
# Signature Detection


def validate_file_signature(context: ValidationContext) -> None:

    extension = context.extension

   
    # 1. Extension must be available
   

    if not extension:
        raise SignatureValidationError(
            f"File extension is unavailable for "
            f"'{context.original_filename}'.",
            phase="integrity_trust",
            check="magic_signature",
            code="EXTENSION_UNAVAILABLE",
        )

    extension = extension.lower().strip()

   
    # 2. Resolve known signatures
   

    expected_signatures = FILE_SIGNATURES.get(extension)

    # Many text-based formats do not have a stable magic signature.
    #
    # Examples:
    #   .txt
    #   .md
    #   .json
    #   .yaml
    #   .py
    #   .js
    #   .csv
    #
    # None means:
    #   "signature validation is not applicable"
    #
    # It does NOT mean:
    #   "signature validation passed"
    if expected_signatures is None:
        context.signature_valid = None
        return

   
    # 3. Determine required read size
   
    required_bytes = max(
        offset + len(signature)
        for offset, signature in expected_signatures
    )

   
    # 4. Read required file header
   
    try:
        with context.file_path.open("rb") as file:
            header = file.read(required_bytes)

    except OSError as exc:
        raise SignatureValidationError(
            f"Unable to read '{context.original_filename}' "
            f"for signature validation.",
            phase="integrity_trust",
            check="magic_signature",
            code="SIGNATURE_READ_FAILED",
        ) from exc

   
    # 5. Validate signature
   
    signature_matches = any(
        len(header) >= offset + len(signature)
        and header[offset:offset + len(signature)] == signature
        for offset, signature in expected_signatures
    )

    if not signature_matches:
        context.signature_valid = False

        raise SignatureValidationError(
            f"Invalid file signature for "
            f"'{context.original_filename}'.",
            phase="integrity_trust",
            check="magic_signature",
            code="INVALID_FILE_SIGNATURE",
        )

   
    # 6. Signature validated

    context.signature_valid = True