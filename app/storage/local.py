import os

from PIL import Image

from app.storage.base import StorageService


class LocalStorageService(StorageService):
    """Development storage: writes files under app/static/uploads.

    Public URLs are returned as a path relative to the site root (e.g.
    "/static/uploads/products/x.jpg"), never with a scheme+host baked in.
    A host prefix would freeze in whatever BASE_URL happened to be set at
    upload time, which then breaks the moment the app is viewed through a
    different domain/tunnel/port — relative URLs work under any of them.
    """

    def __init__(self, base_dir, url_prefix, allowed_mime_types, allowed_extensions, max_size_bytes):
        super().__init__(allowed_mime_types, allowed_extensions, max_size_bytes)
        self.base_dir = base_dir
        self.url_prefix = url_prefix.rstrip("/")
        os.makedirs(self.base_dir, exist_ok=True)

    def upload(self, file_storage, folder="products"):
        ext = self.validate(file_storage)
        object_name = self.build_object_name(folder, file_storage.filename, ext)
        full_path = os.path.join(self.base_dir, object_name)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        file_storage.save(full_path)
        self._optimize(full_path, ext)

        public_url = f"{self.url_prefix}/{object_name}"
        return public_url, object_name

    def delete(self, storage_path):
        full_path = os.path.join(self.base_dir, storage_path)
        if os.path.exists(full_path):
            os.remove(full_path)

    def _optimize(self, full_path, ext):
        if ext not in (".jpg", ".jpeg", ".png", ".webp"):
            return
        try:
            with Image.open(full_path) as img:
                img.verify()
            with Image.open(full_path) as img:
                if img.mode in ("RGBA", "P") and ext in (".jpg", ".jpeg"):
                    img = img.convert("RGB")
                img.thumbnail((1600, 1600))
                img.save(full_path, optimize=True, quality=85)
        except Exception:
            os.remove(full_path)
            raise
