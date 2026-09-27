"""
Upload-safety helpers: never trust client filenames, always generate
server-controlled names, and validate type/size before writing to disk.
"""
import os
import uuid
from pathlib import Path
from typing import Tuple

from fastapi import UploadFile

from app.config import settings

# Magic-byte signatures for the image types we accept — sniffing the
# content is more reliable than trusting the client's declared MIME type.
_SIGNATURES = {
    b"\xff\xd8\xff": ".jpg",
    b"\x89PNG\r\n\x1a\n": ".png",
    b"RIFF": ".webp",  # followed by "....WEBP"; refined in validate_image below
}


class InvalidUploadError(Exception):
    pass


def _sniff_extension(header: bytes) -> str | None:
    if header.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return ".webp"
    return None


def validate_image(file: UploadFile, content: bytes) -> str:
    """
    Validates an uploaded image's real content type and size.
    Returns the safe extension to use for storage. Raises InvalidUploadError otherwise.
    """
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(content) == 0:
        raise InvalidUploadError("Uploaded file is empty.")
    if len(content) > max_bytes:
        raise InvalidUploadError(f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB}MB limit.")

    ext = _sniff_extension(content[:16])
    if ext is None or ext not in settings.ALLOWED_IMAGE_EXTENSIONS:
        raise InvalidUploadError("Unsupported or unrecognized image format.")
    return ext


def build_upload_path(report_id: str, suffix: str, ext: str) -> Tuple[str, str]:
    """
    Builds a server-controlled, path-traversal-safe filename.
    suffix is e.g. "original" or "repair".
    Returns (absolute_path, relative_path_for_db).
    """
    safe_ext = ext if ext.startswith(".") else f".{ext}"
    filename = f"{report_id}_{suffix}_{uuid.uuid4().hex[:8]}{safe_ext}"

    upload_dir = Path(settings.UPLOAD_DIR).resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)

    absolute_path = (upload_dir / filename).resolve()
    # Defense in depth: ensure the resolved path never escapes upload_dir.
    if upload_dir not in absolute_path.parents and absolute_path.parent != upload_dir:
        raise InvalidUploadError("Resolved upload path is invalid.")

    relative_path = os.path.join(os.path.basename(settings.UPLOAD_DIR), filename)
    return str(absolute_path), relative_path


def save_bytes(absolute_path: str, content: bytes) -> None:
    with open(absolute_path, "wb") as f:
        f.write(content)
