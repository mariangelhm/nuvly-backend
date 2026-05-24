from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.database import get_database
from app.core.errors import NuvlyError

logger = logging.getLogger(__name__)


class PricingRepository:
    @staticmethod
    def _public_document(document: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if document is None:
            return None
        sanitized = dict(document)
        sanitized.pop("_id", None)
        return sanitized

    def collection(self, collection_name: str):
        return get_database()[collection_name]

    def database_name(self) -> str:
        return get_database().name

    def insert_document(
        self,
        collection_name: str,
        document: Dict[str, Any],
        duplicate_message: str,
        duplicate_code: str,
    ) -> Dict[str, Any]:
        try:
            self.collection(collection_name).insert_one(document)
        except DuplicateKeyError as exc:
            logger.warning(
                "Pricing duplicate key on insert | database=%s collection=%s id=%s code=%s details=%s",
                self.database_name(),
                collection_name,
                document.get("id"),
                document.get("code") or document.get("componentCode"),
                exc.details,
            )
            raise NuvlyError(duplicate_message, 409, duplicate_code)
        return self._public_document(document)

    def replace_document(
        self,
        collection_name: str,
        document_id: str,
        document: Dict[str, Any],
        not_found_message: str,
        not_found_code: str,
        duplicate_message: str,
        duplicate_code: str,
    ) -> Dict[str, Any]:
        try:
            result = self.collection(collection_name).replace_one({"id": document_id}, document)
        except DuplicateKeyError as exc:
            logger.warning(
                "Pricing duplicate key on replace | database=%s collection=%s id=%s code=%s details=%s",
                self.database_name(),
                collection_name,
                document_id,
                document.get("code") or document.get("componentCode"),
                exc.details,
            )
            raise NuvlyError(duplicate_message, 409, duplicate_code)
        if result.matched_count == 0:
            raise NuvlyError(not_found_message, 404, not_found_code)
        return self._public_document(document)

    def find_document(self, collection_name: str, filters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self._public_document(self.collection(collection_name).find_one(filters, {"_id": 0}))

    def find_documents(
        self,
        collection_name: str,
        filters: Dict[str, Any],
        limit: int = 100,
        skip: int = 0,
        sort_fields: Optional[List[tuple[str, int]]] = None,
    ) -> List[Dict[str, Any]]:
        cursor = self.collection(collection_name).find(filters, {"_id": 0}).skip(skip)
        if sort_fields:
            cursor = cursor.sort(sort_fields)
        if limit > 0:
            cursor = cursor.limit(limit)
        return [self._public_document(document) for document in cursor]

    def update_document_fields(
        self,
        collection_name: str,
        document_id: str,
        updates: Dict[str, Any],
        not_found_message: str,
        not_found_code: str,
    ) -> Dict[str, Any]:
        result = self.collection(collection_name).find_one_and_update(
            {"id": document_id},
            {"$set": updates},
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            raise NuvlyError(not_found_message, 404, not_found_code)
        return self._public_document(result)
