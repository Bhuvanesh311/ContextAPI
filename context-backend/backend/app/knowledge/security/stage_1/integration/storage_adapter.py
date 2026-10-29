import tempfile
from pathlib import Path

from app.infra.storage import storage_service


def download_to_temp_file(
    *,
    bucket: str,
    object_key: str,
    suffix: str = "",
) -> Path:
    
    response = storage_service.download(
        bucket=bucket,
        object_key=object_key,
    )

    temp_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=suffix,
            delete=False,
        ) as temp_file:

            temp_path = Path(temp_file.name)

            while True:
                chunk = response.read(1024 * 1024)

                if not chunk:
                    break

                temp_file.write(chunk)

        return temp_path

    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

        raise

    finally:
        response.close()
        response.release_conn()