"""
Local filesystem image storage for the MVP. The database only ever stores
the relative path + metadata — never the binary.
"""
from fastapi import UploadFile

from app.utils.file_utils import InvalidUploadError, build_upload_path, save_bytes, validate_image


async def store_report_image(report_id: str, file: UploadFile, suffix: str = "original") -> str:
    """
    Validates and persists an uploaded image to disk.
    Returns the relative path to store on the Report/Verification record.
    Raises InvalidUploadError on invalid content.
    """
    content = await file.read()
    ext = validate_image(file, content)
    absolute_path, relative_path = build_upload_path(report_id, suffix, ext)
    save_bytes(absolute_path, content)
    return relative_path


__all__ = ["store_report_image", "InvalidUploadError"]
