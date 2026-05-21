from __future__ import annotations

from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from starlette.requests import Request

from app.core.errors import NuvlyError

PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00"
    b"\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc`\x00\x00\x00\x02\x00\x01"
    b"\xe2!\xbc3"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


class InMemoryMediaCollection:
    def __init__(self) -> None:
        self.documents: list[dict] = []

    def insert_one(self, document: dict) -> None:
        self.documents.append(document)

    def insert_many(self, documents: list[dict], ordered: bool = True) -> None:
        self.documents.extend(documents)

    def delete_many(self, filters: dict) -> None:
        ids = set(filters.get("id", {}).get("$in", []))
        self.documents = [document for document in self.documents if document.get("id") not in ids]


class InMemoryDatabase:
    def __init__(self) -> None:
        self.media_assets = InMemoryMediaCollection()


def _build_test_dir() -> Path:
    directory = Path(".test-temp") / f"nuvly-media-tests-{uuid4().hex}"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _build_request() -> Request:
    return Request(
        {
            "type": "http",
            "scheme": "http",
            "server": ("testserver", 80),
            "root_path": "",
            "path": "/api/media/upload",
            "headers": [],
        }
    )


def test_media_upload_persists_file_and_metadata(monkeypatch) -> None:
    from app.core.config import get_settings
    from app.modules.media import service as media_service

    get_settings.cache_clear()
    settings = get_settings()
    database = InMemoryDatabase()
    test_dir = _build_test_dir()

    monkeypatch.setattr(media_service, "STATIC_DIR", test_dir / "static")
    monkeypatch.setattr(media_service, "get_database", lambda: database)
    monkeypatch.setattr(settings, "public_base_url", None)

    payload = media_service.upload_media_asset(
        file=UploadFile(filename="hero.png", file=BytesIO(PNG_1X1), headers={"content-type": "image/png"}),
        scope="website_template",
        owner_id="tpl_123",
        request=_build_request(),
    )

    assert payload["id"].startswith("asset_")
    assert payload["url"].endswith(f"/static/uploads/website_template/{payload['id']}.png")
    assert payload["thumbnailUrl"] == payload["url"]
    assert payload["mimeType"] == "image/png"
    assert payload["width"] == 1
    assert payload["height"] == 1
    assert payload["size"] == len(PNG_1X1)
    assert payload["scope"] == "website_template"
    assert payload["ownerId"] == "tpl_123"
    assert len(database.media_assets.documents) == 1
    assert (test_dir / "static" / "uploads" / "website_template" / f"{payload['id']}.png").exists()


def test_media_upload_rejects_invalid_file_type(monkeypatch) -> None:
    from app.core.config import get_settings
    from app.modules.media import service as media_service

    get_settings.cache_clear()
    settings = get_settings()
    test_dir = _build_test_dir()

    monkeypatch.setattr(media_service, "STATIC_DIR", test_dir / "static")
    monkeypatch.setattr(media_service, "get_database", lambda: InMemoryDatabase())
    monkeypatch.setattr(settings, "public_base_url", None)

    try:
        media_service.upload_media_asset(
            file=UploadFile(filename="notes.txt", file=BytesIO(b"hello"), headers={"content-type": "text/plain"}),
            scope=None,
            owner_id=None,
            request=_build_request(),
        )
    except NuvlyError as exc:
        assert exc.code == "INVALID_FILE_TYPE"
        assert exc.status_code == 400
    else:
        raise AssertionError("Expected invalid file type error")


def test_media_route_is_registered_in_openapi() -> None:
    import app.main as main_module

    paths = main_module.app.openapi()["paths"]
    assert "/api/media/upload" in paths
    assert "post" in paths["/api/media/upload"]
    assert "/api/media/upload-batch" in paths
    assert "post" in paths["/api/media/upload-batch"]


def test_media_batch_upload_persists_all_assets(monkeypatch) -> None:
    from app.core.config import get_settings
    from app.modules.media import service as media_service

    get_settings.cache_clear()
    settings = get_settings()
    database = InMemoryDatabase()
    test_dir = _build_test_dir()

    monkeypatch.setattr(media_service, "STATIC_DIR", test_dir / "static")
    monkeypatch.setattr(media_service, "get_database", lambda: database)
    monkeypatch.setattr(settings, "public_base_url", None)

    payload = media_service.upload_media_assets_batch(
        files=[
            UploadFile(filename="hero.png", file=BytesIO(PNG_1X1), headers={"content-type": "image/png"}),
            UploadFile(filename="gallery.png", file=BytesIO(PNG_1X1), headers={"content-type": "image/png"}),
        ],
        scope="website_template",
        owner_id="tpl_123",
        client_keys=[
            "blocks.blk_hero.props.mediaImage",
            "blocks.blk_gallery.props.images.0",
        ],
        request=_build_request(),
    )

    assert payload["errors"] == []
    assert len(payload["assets"]) == 2
    assert payload["assets"][0]["clientKey"] == "blocks.blk_hero.props.mediaImage"
    assert payload["assets"][1]["clientKey"] == "blocks.blk_gallery.props.images.0"
    assert len(database.media_assets.documents) == 2


def test_media_batch_upload_rejects_too_many_files(monkeypatch) -> None:
    from app.core.config import get_settings
    from app.modules.media import service as media_service

    get_settings.cache_clear()
    settings = get_settings()
    test_dir = _build_test_dir()

    monkeypatch.setattr(media_service, "STATIC_DIR", test_dir / "static")
    monkeypatch.setattr(media_service, "get_database", lambda: InMemoryDatabase())
    monkeypatch.setattr(settings, "public_base_url", None)

    files = [
        UploadFile(filename=f"image-{index}.png", file=BytesIO(PNG_1X1), headers={"content-type": "image/png"})
        for index in range(21)
    ]

    try:
        media_service.upload_media_assets_batch(
            files=files,
            scope="general",
            owner_id=None,
            client_keys=None,
            request=_build_request(),
        )
    except NuvlyError as exc:
        assert exc.code == "TOO_MANY_FILES"
        assert exc.status_code == 400
    else:
        raise AssertionError("Expected too many files error")


def test_media_batch_upload_rejects_whole_batch_on_validation_error(monkeypatch) -> None:
    from app.core.config import get_settings
    from app.modules.media import service as media_service

    get_settings.cache_clear()
    settings = get_settings()
    database = InMemoryDatabase()
    test_dir = _build_test_dir()

    monkeypatch.setattr(media_service, "STATIC_DIR", test_dir / "static")
    monkeypatch.setattr(media_service, "get_database", lambda: database)
    monkeypatch.setattr(settings, "public_base_url", None)

    try:
        media_service.upload_media_assets_batch(
            files=[
                UploadFile(filename="hero.png", file=BytesIO(PNG_1X1), headers={"content-type": "image/png"}),
                UploadFile(filename="bad.txt", file=BytesIO(b"oops"), headers={"content-type": "text/plain"}),
            ],
            scope="website_template",
            owner_id="tpl_123",
            client_keys=["blocks.blk_hero.props.mediaImage", "blocks.blk_gallery.props.images.0"],
            request=_build_request(),
        )
    except NuvlyError as exc:
        assert exc.code == "INVALID_FILE_TYPE"
        assert exc.status_code == 400
    else:
        raise AssertionError("Expected invalid file type error")

    assert database.media_assets.documents == []
