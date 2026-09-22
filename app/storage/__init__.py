from app.storage.base import StorageService, UnsupportedFileError
from app.storage.local import LocalStorageService
from app.storage.gcs import GCSStorageService

_storage_instance = None


def init_storage(app):
    global _storage_instance
    if app.config.get("GCS_ENABLED"):
        _storage_instance = GCSStorageService(
            bucket_name=app.config["GCS_BUCKET_NAME"],
            allowed_mime_types=app.config["ALLOWED_IMAGE_MIME_TYPES"],
            allowed_extensions=app.config["ALLOWED_IMAGE_EXTENSIONS"],
            max_size_bytes=app.config["UPLOAD_MAX_SIZE_BYTES"],
        )
    else:
        _storage_instance = LocalStorageService(
            base_dir=app.config["UPLOAD_LOCAL_DIR"],
            url_prefix="/static/uploads",
            allowed_mime_types=app.config["ALLOWED_IMAGE_MIME_TYPES"],
            allowed_extensions=app.config["ALLOWED_IMAGE_EXTENSIONS"],
            max_size_bytes=app.config["UPLOAD_MAX_SIZE_BYTES"],
        )
    return _storage_instance


def get_storage():
    if _storage_instance is None:
        raise RuntimeError("Storage service not initialized. Call init_storage(app) first.")
    return _storage_instance


__all__ = ["StorageService", "UnsupportedFileError", "LocalStorageService", "GCSStorageService", "init_storage", "get_storage"]
