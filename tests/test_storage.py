import io

import pytest
from werkzeug.datastructures import FileStorage

from app.storage.base import UnsupportedFileError
from app.storage.local import LocalStorageService
from tests.conftest import fake_image_bytes


@pytest.fixture()
def local_storage(tmp_path, app):
    return LocalStorageService(
        base_dir=str(tmp_path),
        url_prefix="/static/uploads",
        allowed_mime_types={"image/png", "image/jpeg", "image/webp"},
        allowed_extensions={".png", ".jpg", ".jpeg", ".webp"},
        max_size_bytes=2 * 1024 * 1024,
    )


def test_upload_valid_image(local_storage):
    fs = FileStorage(stream=fake_image_bytes(), filename="photo.png", content_type="image/png")
    url, path = local_storage.upload(fs, folder="products")
    assert url.endswith(path)
    assert path.startswith("products/")


def test_upload_returns_relative_url_not_tied_to_a_host(local_storage):
    """Regression: the URL must be root-relative (e.g. /static/uploads/...),
    never scheme+host, so it keeps working when the app is viewed through a
    different domain, port, or tunnel than the one active at upload time."""
    fs = FileStorage(stream=fake_image_bytes(), filename="photo.png", content_type="image/png")
    url, _path = local_storage.upload(fs, folder="products")
    assert url.startswith("/static/uploads/")
    assert "://" not in url


def test_rejects_disallowed_extension(local_storage):
    fs = FileStorage(stream=io.BytesIO(b"not really an exe"), filename="malware.exe", content_type="application/octet-stream")
    with pytest.raises(UnsupportedFileError):
        local_storage.upload(fs, folder="products")


def test_rejects_mismatched_mime_type(local_storage):
    fs = FileStorage(stream=io.BytesIO(b"fake"), filename="photo.png", content_type="application/octet-stream")
    with pytest.raises(UnsupportedFileError):
        local_storage.upload(fs, folder="products")


def test_rejects_oversized_file(local_storage):
    big = io.BytesIO(b"0" * (3 * 1024 * 1024))
    fs = FileStorage(stream=big, filename="huge.png", content_type="image/png")
    with pytest.raises(UnsupportedFileError):
        local_storage.upload(fs, folder="products")


def test_rejects_non_image_content_disguised_as_png(local_storage):
    fs = FileStorage(stream=io.BytesIO(b"<?php echo 'hacked'; ?>"), filename="fake.png", content_type="image/png")
    with pytest.raises(Exception):
        local_storage.upload(fs, folder="products")


def test_rejects_empty_file(local_storage):
    fs = FileStorage(stream=io.BytesIO(b""), filename="empty.png", content_type="image/png")
    with pytest.raises(UnsupportedFileError):
        local_storage.upload(fs, folder="products")
