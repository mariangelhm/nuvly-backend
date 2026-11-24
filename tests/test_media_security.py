import asyncio
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, UploadFile
from test_media_upload import PNG_1X1, _build_request

from app.core.errors import NuvlyError, register_exception_handlers
from app.modules.auth.dependencies import get_current_user
from app.modules.media import routes, service
from app.modules.media.limits import MediaRequestLimitMiddleware


def request(app, body, headers):
    messages = []

    async def run():
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            messages.append(message)

        await app(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": "/api/media/upload",
                "root_path": "",
                "query_string": b"",
                "headers": headers,
                "server": ("test", 80),
                "client": ("test", 1),
            },
            receive,
            send,
        )

    asyncio.run(run())
    return next(m["status"] for m in messages if m["type"] == "http.response.start")


def test_upload_requires_login_and_ignores_forged_owner(monkeypatch):
    monkeypatch.setattr(routes, "consume_rate_limit", lambda *a, **k: None)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(routes.router, prefix="/api")
    body = (
        b'--test\r\nContent-Disposition: form-data; name="ownerId"\r\n\r\nother-user\r\n'
        b'--test\r\nContent-Disposition: form-data; name="file"; filename="test.png"\r\nContent-Type: image/png\r\n\r\n'
        + PNG_1X1
        + b"\r\n--test--\r\n"
    )
    headers = [(b"content-type", b"multipart/form-data; boundary=test")]
    assert request(app, body, headers) == 401
    app.dependency_overrides[get_current_user] = lambda: {"id": "real-owner", "accountType": "customer"}
    observed = []

    def upload(**kwargs):
        observed.append(kwargs["owner_id"])
        return {
            "id": "asset",
            "url": "/asset.png",
            "thumbnailUrl": "/asset.png",
            "mimeType": "image/png",
            "width": 1,
            "height": 1,
            "size": 1,
            "scope": "general",
            "ownerId": kwargs["owner_id"],
            "createdAt": "2026-11-14T00:00:00Z",
        }

    monkeypatch.setattr(routes, "upload_media_asset", upload)
    assert request(app, body, headers) == 201
    assert observed == ["real-owner"]


@pytest.mark.parametrize("declared", [True, False])
def test_request_body_limit_precedes_multipart_buffering(declared):
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    app.add_middleware(MediaRequestLimitMiddleware, api_prefix="/api", max_file_bytes=1)
    headers = [(b"content-type", b"multipart/form-data; boundary=test")]
    body = b"x" * 140_000
    if declared:
        headers.append((b"content-length", str(len(body)).encode()))
    assert request(app, body, headers) == 413


@pytest.mark.parametrize(
    "content_type,content,code",
    [
        ("image/svg+xml", b'<svg width="1" height="1"><script>alert(1)</script></svg>', "INVALID_FILE_TYPE"),
        ("image/png", PNG_1X1[:24], "INVALID_IMAGE"),
    ],
)
def test_active_svg_and_truncated_raster_are_rejected(monkeypatch, tmp_path, content_type, content, code):
    monkeypatch.setattr(service, "STATIC_DIR", tmp_path)
    with pytest.raises(NuvlyError) as exc:
        service._build_asset_payload(
            file=UploadFile(filename="image", file=BytesIO(content), headers={"content-type": content_type}),
            scope="general",
            owner_id="owner",
            request=_build_request(),
        )
    assert exc.value.code == code


def test_oversized_file_is_only_read_to_limit_plus_one(monkeypatch):
    class BoundedFile(BytesIO):
        def read(self, size=-1):
            assert size == 5
            return b"12345"

    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace(media_max_size_bytes=4, media_max_size_mb=1))
    with pytest.raises(NuvlyError) as exc:
        service._build_asset_payload(
            file=UploadFile(filename="image.png", file=BoundedFile(), headers={"content-type": "image/png"}),
            scope="general",
            owner_id="owner",
            request=_build_request(),
        )
    assert exc.value.code == "FILE_TOO_LARGE"
