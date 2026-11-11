import hashlib


def sha256_bytes(data: bytes) -> str:
    """Stable content hash used to detect identical PDF uploads."""
    return hashlib.sha256(data).hexdigest()