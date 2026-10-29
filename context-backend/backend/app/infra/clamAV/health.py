from app.infra.clamAV.client import clamav_client
from app.infra.clamAV.exceptions import ClamAVConnectionError


def check_clamav_health() -> bool:
    """
    Verify that the ClamAV server is reachable.
    """

    try:
        return bool(clamav_client.ping())

    except Exception as exc:
        raise ClamAVConnectionError(
            "Unable to connect to the ClamAV server."
        ) from exc