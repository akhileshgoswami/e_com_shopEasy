import os
import uuid
from abc import ABC, abstractmethod

from werkzeug.utils import secure_filename


class UnsupportedFileError(ValueError):
    pass


class StorageService(ABC):
    """Abstraction over where uploaded images are persisted.

    Implementations: LocalStorageService (dev), GCSStorageService (production).
    """

    def __init__(self, allowed_mime_types, allowed_extensions, max_size_bytes):
        self.allowed_mime_types = allowed_mime_types
        self.allowed_extensions = allowed_extensions
        self.max_size_bytes = max_size_bytes

    def validate(self, file_storage):
        if file_storage is None or not file_storage.filename:
            raise UnsupportedFileError("No file provided.")

        ext = os.path.splitext(file_storage.filename)[1].lower()
        if ext not in self.allowed_extensions:
            raise UnsupportedFileError(f"File extension '{ext}' is not allowed.")

        mime_type = file_storage.mimetype
        if mime_type not in self.allowed_mime_types:
            raise UnsupportedFileError(f"File type '{mime_type}' is not allowed.")

        file_storage.stream.seek(0, os.SEEK_END)
        size = file_storage.stream.tell()
        file_storage.stream.seek(0)
        if size > self.max_size_bytes:
            raise UnsupportedFileError("File exceeds maximum allowed size.")
        if size == 0:
            raise UnsupportedFileError("File is empty.")

        return ext

    def build_object_name(self, folder, filename, ext):
        safe_name = secure_filename(os.path.splitext(filename)[0]) or "file"
        unique = uuid.uuid4().hex[:12]
        return f"{folder}/{safe_name}-{unique}{ext}"

    @abstractmethod
    def upload(self, file_storage, folder="products"):
        """Validate and store file_storage under folder. Returns (public_url, storage_path)."""
        raise NotImplementedError

    @abstractmethod
    def delete(self, storage_path):
        raise NotImplementedError
