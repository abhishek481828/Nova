"""Protocol Version Negotiation for Nova v2.0."""

from typing import Tuple


class VersionNegotiationError(Exception):
    """Raised when protocol versions are incompatible."""
    pass


class VersionNegotiator:
    CORE_VERSION = "2.0.0"
    MIN_SUPPORTED_VERSION = "2.0.0"
    MAX_SUPPORTED_VERSION = "2.5.0"

    @classmethod
    def parse_version_tuple(cls, version_str: str) -> Tuple[int, int, int]:
        try:
            parts = version_str.split(".")
            return int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0
        except Exception:
            return (2, 0, 0)

    @classmethod
    def negotiate(cls, companion_version: str) -> str:
        """Negotiates compatible protocol version between Core and Companion."""
        comp_tuple = cls.parse_version_tuple(companion_version)
        min_tuple = cls.parse_version_tuple(cls.MIN_SUPPORTED_VERSION)
        max_tuple = cls.parse_version_tuple(cls.MAX_SUPPORTED_VERSION)

        if comp_tuple < min_tuple:
            raise VersionNegotiationError(
                f"Companion version {companion_version} is below minimum supported version {cls.MIN_SUPPORTED_VERSION}"
            )
        
        # If companion is within range, select minimum common version
        if comp_tuple <= max_tuple:
            return companion_version
        
        return cls.MAX_SUPPORTED_VERSION
