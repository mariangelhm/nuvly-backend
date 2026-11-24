"""Prevent browsers and shared caches from retaining private API responses."""


class SecurityHeadersMiddleware:
    def __init__(self, app, *, api_prefix):
        self.app = app
        self.prefix = api_prefix.rstrip("/")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        private = any(
            path == self.prefix + section or path.startswith(self.prefix + section + "/")
            for section in ("/auth", "/admin", "/studio", "/customer", "/payments", "/media")
        )

        async def secured_send(message):
            if message["type"] == "http.response.start":
                headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() not in {b"x-content-type-options", b"referrer-policy"}
                    and not (private and key.lower() == b"cache-control")
                ]
                headers.extend([(b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"no-referrer")])
                if private:
                    headers.append((b"cache-control", b"no-store"))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, secured_send)
