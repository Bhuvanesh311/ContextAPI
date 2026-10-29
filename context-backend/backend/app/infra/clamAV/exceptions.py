class ClamAVError(Exception):
    """Base exception for ClamAV."""


class ClamAVConnectionError(ClamAVError):
    """Raised when ClamAV cannot be reached."""


class ClamAVScanError(ClamAVError):
    """Raised when malware scanning fails."""


class MalwareDetectedError(ClamAVError):
    """Raised when malware is detected."""