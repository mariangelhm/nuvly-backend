from functools import partial
from typing import Any

from google.auth import exceptions
from google.auth.transport.requests import Request
from google.oauth2 import id_token

from app.core.errors import NuvlyError


def verify_google_credential(credential: str, client_id: str) -> dict[str, Any]:
    try:
        # Google's library checks the signature, issuer, audience and expiry.
        return id_token.verify_oauth2_token(credential, partial(Request(), timeout=10), audience=client_id)
    except exceptions.TransportError as exc:
        raise NuvlyError(
            "No pudimos conectar con Google. Inténtalo nuevamente.", 503, "GOOGLE_AUTH_UNAVAILABLE"
        ) from exc
    except (ValueError, exceptions.GoogleAuthError) as exc:
        raise NuvlyError(
            "No pudimos verificar tu acceso con Google. Inténtalo nuevamente.", 401, "INVALID_GOOGLE_CREDENTIAL"
        ) from exc
