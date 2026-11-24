from fastapi import HTTPException
from starlette.responses import JSONResponse


class MediaRequestLimitMiddleware:
    """Reject oversized multipart bodies before parsing or buffering them."""

    def __init__(self, app, *, api_prefix: str, max_file_bytes: int):
        self.app = app
        self.prefix = api_prefix.rstrip("/") + "/media/"
        self.max_file_bytes = max_file_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith(self.prefix):
            return await self.app(scope, receive, send)
        limit = self.max_file_bytes * (20 if scope["path"].endswith("/upload-batch") else 1) + 128 * 1024
        headers = dict(scope.get("headers", []))
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            declared = limit + 1
        if declared > limit or declared < 0:
            return await JSONResponse(
                {"error": {"code": "UPLOAD_BODY_TOO_LARGE", "message": "Archivo demasiado grande."}}, status_code=413
            )(scope, receive, send)
        consumed = 0

        async def bounded_receive():
            nonlocal consumed
            message = await receive()
            consumed += len(message.get("body", b""))
            if consumed > limit:
                raise HTTPException(413, "Archivo demasiado grande.")
            return message

        await self.app(scope, bounded_receive, send)


class UploadedAssetHeadersMiddleware:
    """Keep already stored SVG documents inert when opened directly."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        async def secure_send(message):
            if message["type"] == "http.response.start" and scope.get("path", "").startswith("/static/uploads/"):
                message = {**message, "headers": [*message.get("headers", []), (b"x-content-type-options", b"nosniff")]}
                if scope["path"].lower().endswith(".svg"):
                    message["headers"].append(
                        (b"content-security-policy", b"sandbox; default-src 'none'; style-src 'unsafe-inline'")
                    )
            await send(message)

        await self.app(scope, receive, secure_send)
