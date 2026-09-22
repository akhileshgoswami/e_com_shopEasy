import io

from PIL import Image
from google.cloud import storage as gcs_storage

from app.storage.base import StorageService


class GCSStorageService(StorageService):
    """Production storage: writes files to a Google Cloud Storage bucket."""

    def __init__(self, bucket_name, allowed_mime_types, allowed_extensions, max_size_bytes):
        super().__init__(allowed_mime_types, allowed_extensions, max_size_bytes)
        self.bucket_name = bucket_name
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = gcs_storage.Client()
        return self._client

    @property
    def bucket(self):
        return self.client.bucket(self.bucket_name)

    def upload(self, file_storage, folder="products"):
        ext = self.validate(file_storage)
        object_name = self.build_object_name(folder, file_storage.filename, ext)

        image_bytes = self._optimize(file_storage, ext)

        blob = self.bucket.blob(object_name)
        content_type = file_storage.mimetype
        blob.upload_from_file(io.BytesIO(image_bytes), content_type=content_type, rewind=True)

        public_url = f"https://storage.googleapis.com/{self.bucket_name}/{object_name}"
        return public_url, object_name

    def delete(self, storage_path):
        blob = self.bucket.blob(storage_path)
        if blob.exists():
            blob.delete()

    def _optimize(self, file_storage, ext):
        file_storage.stream.seek(0)
        raw = file_storage.stream.read()
        try:
            img = Image.open(io.BytesIO(raw))
            img.verify()
            img = Image.open(io.BytesIO(raw))
            if img.mode in ("RGBA", "P") and ext in (".jpg", ".jpeg"):
                img = img.convert("RGB")
            img.thumbnail((1600, 1600))
            buffer = io.BytesIO()
            save_format = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP"}[ext.lstrip(".")]
            img.save(buffer, format=save_format, optimize=True, quality=85)
            return buffer.getvalue()
        except Exception as exc:
            raise ValueError("Uploaded file is not a valid image.") from exc
