import os
import uuid
from datetime import datetime

import firebase_admin
from firebase_admin import credentials, storage
from fastapi import UploadFile

from core.config import settings
import logging

logger = logging.getLogger(__name__)


ALLOWED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".png", ".jpg", ".jpeg",
    ".ppt", ".pptx", ".xlsx", ".csv", ".zip",
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _init_firebase():
    """Initialise the Firebase app once (idempotent)."""
    if not firebase_admin._apps:
        cred_path = settings.FIREBASE_CREDENTIALS_PATH or os.getenv(
            "FIREBASE_CREDENTIALS_PATH", "firebase-credentials.json"
        )
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred, {
            "storageBucket": settings.FIREBASE_STORAGE_BUCKET
            or os.getenv("FIREBASE_STORAGE_BUCKET"),
        })


def _safe_filename(original: str) -> str:
    """Return a unique, sanitised blob name preserving the original extension."""
    ext = os.path.splitext(original)[1].lower()
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    unique = uuid.uuid4().hex[:8]
    return f"{timestamp}_{unique}{ext}"


def _validate_file(file: UploadFile):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"File type '{ext}' is not allowed.")


async def upload_file_to_firebase(file: UploadFile, folder: str = "onboarding") -> str:

    print(f"file: {file}, folder: {folder}")

    """
    Upload a single file to Firebase Storage and return its public URL.

    Raises ValueError for invalid file types or files exceeding the size limit.
    """
    _init_firebase()
    _validate_file(file)

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise ValueError(
            f"File '{file.filename}' exceeds the {MAX_FILE_SIZE // (1024 * 1024)} MB limit."
        )

    blob_name = f"{folder}/{_safe_filename(file.filename or 'document')}"
    bucket = storage.bucket()
    blob = bucket.blob(blob_name)
    blob.upload_from_string(content, content_type=file.content_type)
    # blob.make_public()
    # return blob.public_url
    return f"https://storage.googleapis.com/{bucket.name}/{blob_name}"


async def upload_documents(files: dict[str, UploadFile | None], folder: str = "onboarding") -> dict[str, str]:
    """
    Upload multiple named document files to Firebase Storage.

    Parameters
    ----------
    files : dict mapping field name -> UploadFile (or None if not provided)
    folder : storage folder prefix

    Returns
    -------
    dict mapping field name -> public URL for every file that was uploaded.
    """
    logger.info(f"Starting upload_documents with folder='{folder}', file count={len(files)}")
    
    urls: dict[str, str] = {}
    for field_name, file in files.items():
        if file is None or not file.filename:
            logger.debug(f"Skipping field '{field_name}': file is None or has no filename")
            continue
        try:
            url = await upload_file_to_firebase(file, folder=folder)
            urls[field_name] = url
            logger.info(f"Successfully uploaded '{field_name}' ({file.filename})")
        except Exception as e:
            logger.error(f"Failed to upload '{field_name}': {e}")
            raise
    
    logger.info(f"Upload complete: {len(urls)} files uploaded")
    return urls
