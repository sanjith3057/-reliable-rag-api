import hashlib


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def doc_id_for(data: bytes) -> str:
    """The document ID is derived from the bytes, so identical content always maps to the same ID."""
    return content_hash(data)[:16]
