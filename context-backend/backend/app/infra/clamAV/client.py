import pyclamd

from app.infra.clamAV.config import (
    CLAMAV_HOST,
    CLAMAV_PORT,
)


clamav_client = pyclamd.ClamdNetworkSocket(
    host=CLAMAV_HOST,
    port=CLAMAV_PORT,
)