"""
Upload-safety helpers: never trust client filenames, always generate
server-controlled names, and validate type/size before writing to disk.

Path strategy
─────────────
All paths are resolved from BASE_DIR (the project root, derived from this
file's location) so the server works correctly regardless of the working
directory uvicorn is started from.

Storage layout on disk:
    <project-root>/app/uploads/reports/<report_id>_<suffix>_<rand>.<ext>

URL path stored in the database and returned to clients:
    /uploads/reports/<filename>

The /uploads StaticFiles mount in main.py serves these files at:
    http://<host>:8000/uploads/reports/<filename>
"""
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.config import settings

# Project root is two levels up from this file:
#   app/utils/file_utils.py → app/utils/ → app/ → project root
_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_UPLOAD_ROOT = _BASE_DIR / "app" / "uploads"

# Magic-byte signatures for the image types we accept — sniffing the
# content is more reliable than trusting the client's declared MIME type.
_SIGNATURES = {
    b"\xff\xd8\xff": ".jpg",
    b"\x89PNG\r\n\x1a\n": ".png",
    b"RIFF": ".webp",  # followed by "....WEBP"; refined in _sniff_extension
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


def build_upload_path(report_id: str, suffix: str, ext: str) -> tuple[str, str]:
    """
    Builds a server-controlled, path-traversal-safe filename.
    suffix is e.g. "original" or "repair".

    Returns:
        absolute_path  – full filesystem path for writing the file
        url_path       – public URL path stored in DB: /uploads/reports/<filename>
    """
    safe_ext = ext if ext.startswith(".") else f".{ext}"
    filename = f"{report_id}_{suffix}_{uuid.uuid4().hex[:8]}{safe_ext}"

    # Always use the subdirectory name from settings (e.g. "app/uploads/reports")
    # but resolve it against our BASE_DIR-anchored root, never CWD.
    subdir_name = Path(settings.UPLOAD_DIR).name  # → "reports"
    upload_dir = _UPLOAD_ROOT / subdir_name
    upload_dir.mkdir(parents=True, exist_ok=True)

    absolute_path = (upload_dir / filename).resolve()

    # Defense in depth: ensure the resolved path never escapes upload_dir.
    if upload_dir not in absolute_path.parents and absolute_path.parent != upload_dir:
        raise InvalidUploadError("Resolved upload path is invalid.")

    # URL path the mobile app will use to fetch the image:
    #   /uploads/reports/<filename>
    url_path = f"/uploads/{subdir_name}/{filename}"

    return str(absolute_path), url_path


def resolve_absolute_image_path(url_path: str) -> Path:
    """
    Given a stored url_path like /uploads/reports/abc.jpg,
    returns the absolute filesystem path.

    Also handles legacy paths like 'reports/abc.jpg' or
    'app/uploads/reports/abc.jpg' stored before this fix.
    """
    p = url_path.lstrip("/")

    # Strip leading 'app/' if present (legacy paths)
    if p.startswith("app/"):
        p = p[len("app/"):]

    # Now p is either 'uploads/reports/filename' or 'reports/filename'
    if p.startswith("uploads/"):
        return (_UPLOAD_ROOT / p[len("uploads/"):]).resolve()
    else:
        return (_UPLOAD_ROOT / p).resolve()


def save_bytes(absolute_path: str, content: bytes) -> None:
    with open(absolute_path, "wb") as f:
        f.write(content)
