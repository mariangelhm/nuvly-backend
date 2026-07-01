from __future__ import annotations

import logging
from typing import Any

from pymongo.errors import DuplicateKeyError

from app.core.database import get_database
from app.core.errors import NuvlyError

logger = logging.getLogger(__name__)


class AuthRepository:
    def collection(self, collection_name: str):
        return get_database()[collection_name]

    @staticmethod
    def _public_document(document: dict[str, Any] | None) -> dict[str, Any] | None:
        if document is None:
            return None
        sanitized = dict(document)
        sanitized.pop("_id", None)
        return sanitized

    @staticmethod
    def _duplicate_details(exc: DuplicateKeyError) -> tuple[dict[str, Any], dict[str, Any]]:
        details = exc.details or {}
        return details.get("keyPattern") or {}, details.get("keyValue") or {}

    def find_user_by_email(self, email_normalized: str) -> dict[str, Any] | None:
        return self._public_document(
            self.collection("users").find_one({"emailNormalized": email_normalized}, {"_id": 0})
        )

    def find_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        return self._public_document(
            self.collection("users").find_one({"id": user_id}, {"_id": 0})
        )

    def insert_user(self, document: dict[str, Any]) -> dict[str, Any]:
        try:
            self.collection("users").insert_one(document)
        except DuplicateKeyError as exc:
            key_pattern, key_value = self._duplicate_details(exc)
            logger.warning(
                "Duplicate auth user insert | email=%s keyPattern=%s keyValue=%s",
                document.get("emailNormalized"),
                key_pattern,
                key_value,
            )
            if "emailNormalized" in key_pattern or "emailNormalized" in key_value:
                raise NuvlyError(
                    "Ya existe una cuenta registrada con ese email.",
                    409,
                    "EMAIL_ALREADY_REGISTERED",
                ) from exc
            raise NuvlyError("Conflicto duplicado al crear usuario.", 500, "AUTH_DUPLICATE_KEY") from exc
        return self._public_document(document) or {}

    def replace_user(self, user_id: str, document: dict[str, Any]) -> dict[str, Any]:
        result = self.collection("users").replace_one({"id": user_id}, document)
        if result.matched_count == 0:
            raise NuvlyError("Usuario no encontrado.", 404, "USER_NOT_FOUND")
        return self._public_document(document) or {}

    def insert_session(self, document: dict[str, Any]) -> dict[str, Any]:
        try:
            self.collection("auth_sessions").insert_one(document)
        except DuplicateKeyError as exc:
            logger.warning("Duplicate auth session insert | sessionId=%s", document.get("id"))
            raise NuvlyError("No se pudo crear la sesión.", 500, "AUTH_SESSION_DUPLICATE") from exc
        return self._public_document(document) or {}

    def find_session_by_token_hash(self, token_hash: str) -> dict[str, Any] | None:
        return self._public_document(
            self.collection("auth_sessions").find_one({"tokenHash": token_hash}, {"_id": 0})
        )

    def replace_session(self, session_id: str, document: dict[str, Any]) -> dict[str, Any]:
        result = self.collection("auth_sessions").replace_one({"id": session_id}, document)
        if result.matched_count == 0:
            raise NuvlyError("Sesion no encontrada.", 404, "SESSION_NOT_FOUND")
        return self._public_document(document) or {}

    def insert_password_reset_token(self, document: dict[str, Any]) -> dict[str, Any]:
        try:
            self.collection("password_reset_tokens").insert_one(document)
        except DuplicateKeyError as exc:
            logger.warning("Duplicate password reset token insert | id=%s", document.get("id"))
            raise NuvlyError("No se pudo generar el token de recuperacion.", 500, "RESET_TOKEN_DUPLICATE") from exc
        return self._public_document(document) or {}

    def find_password_reset_token_by_hash(self, token_hash: str) -> dict[str, Any] | None:
        return self._public_document(
            self.collection("password_reset_tokens").find_one({"tokenHash": token_hash}, {"_id": 0})
        )

    def replace_password_reset_token(self, token_id: str, document: dict[str, Any]) -> dict[str, Any]:
        result = self.collection("password_reset_tokens").replace_one({"id": token_id}, document)
        if result.matched_count == 0:
            raise NuvlyError("Token de recuperacion no encontrado.", 404, "RESET_TOKEN_NOT_FOUND")
        return self._public_document(document) or {}
