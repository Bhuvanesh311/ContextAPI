from app.infra.clamAV.client import clamav_client
from app.infra.clamAV.exceptions import (
    ClamAVConnectionError,
    ClamAVScanError,
)


class ClamAVService:
    """
    Service abstraction for ClamAV.
    """

    def ping(self) -> bool:
        """
        Verify that ClamAV is reachable.
        """

        try:
            return bool(clamav_client.ping())

        except Exception as exc:
            raise ClamAVConnectionError(
                "Unable to connect to the ClamAV server."
            ) from exc

    def scan_stream(
        self,
        file_data: bytes,
    ):
        """
        Scan an in-memory file.
        """

        try:
            return clamav_client.scan_stream(file_data)

        except Exception as exc:
            raise ClamAVScanError(
                "Failed to scan file."
            ) from exc


clamav_service = ClamAVService()