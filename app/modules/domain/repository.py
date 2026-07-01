import logging
from typing import Any, Dict, List, Optional

from pymongo.errors import DuplicateKeyError

from app.core.database import get_database
from app.core.errors import NuvlyError

logger = logging.getLogger(__name__)


class DomainRepository:
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

    @staticmethod
    def _duplicate_key_context(exc: DuplicateKeyError) -> Dict[str, Any]:
        details = exc.details or {}
        key_pattern = details.get("keyPattern") or {}
        key_value = details.get("keyValue") or {}
        index_name = details.get("indexName") or details.get("index")
        return {
            "details": details,
            "index_name": index_name,
            "key_pattern": key_pattern,
            "key_value": key_value,
            "is_slug_duplicate": "slug" in key_pattern or "slug" in key_value,
            "is_code_duplicate": "codeNormalized" in key_pattern or "codeNormalized" in key_value or "code" in key_pattern or "code" in key_value,
        }

    def insert_document(
        self,
        collection_name: str,
        document: Dict[str, Any],
        duplicate_message: str,
        duplicate_code: str = "DUPLICATED_SLUG",
    ) -> Dict[str, Any]:
        try:
            self.collection(collection_name).insert_one(document)
        except DuplicateKeyError as exc:
            context = self._duplicate_key_context(exc)
            logger.warning(
                "Duplicate key on insert | database=%s collection=%s slug=%s id=%s indexName=%s keyPattern=%s keyValue=%s details=%s",
                self.database_name(),
                collection_name,
                document.get("slug"),
                document.get("id"),
                context["index_name"],
                context["key_pattern"],
                context["key_value"],
                context["details"],
            )
            if context["is_slug_duplicate"] or context["is_code_duplicate"]:
                raise NuvlyError(duplicate_message, 409, duplicate_code)
            raise NuvlyError(
                f"Mongo duplicate key conflict in {collection_name}. Check logs for index details.",
                500,
                "MONGO_DUPLICATE_KEY",
            )
        return self._public_document(document)

    def find_documents(
        self,
        collection_name: str,
        filters: Dict[str, Any],
        limit: int = 20,
        skip: int = 0,
        sort_field: str = "updatedAt",
        sort_direction: int = -1,
    ) -> List[Dict[str, Any]]:
        cursor = self.collection(collection_name).find(filters, {"_id": 0}).sort(sort_field, sort_direction).skip(skip)
        if limit > 0:
            cursor = cursor.limit(limit)
        return [self._public_document(document) for document in cursor]

    def find_document(self, collection_name: str, filters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self._public_document(self.collection(collection_name).find_one(filters, {"_id": 0}))

    def find_document_by_slug(self, collection_name: str, slug: str) -> Optional[Dict[str, Any]]:
        filters = {"slug": slug}
        document = self.find_document(collection_name, filters)
        logger.info(
            "Slug lookup | database=%s collection=%s slug=%s found=%s foundId=%s",
            self.database_name(),
            collection_name,
            slug,
            document is not None,
            document.get("id") if document else None,
        )
        return document

    def replace_document(
        self,
        collection_name: str,
        document_id: str,
        document: Dict[str, Any],
        not_found_message: str,
        not_found_code: str,
        duplicate_message: str,
        duplicate_code: str = "DUPLICATED_SLUG",
    ) -> Dict[str, Any]:
        try:
            result = self.collection(collection_name).replace_one({"id": document_id}, document)
        except DuplicateKeyError as exc:
            context = self._duplicate_key_context(exc)
            logger.warning(
                "Duplicate key on replace | database=%s collection=%s slug=%s id=%s indexName=%s keyPattern=%s keyValue=%s details=%s",
                self.database_name(),
                collection_name,
                document.get("slug"),
                document_id,
                context["index_name"],
                context["key_pattern"],
                context["key_value"],
                context["details"],
            )
            if context["is_slug_duplicate"] or context["is_code_duplicate"]:
                raise NuvlyError(duplicate_message, 409, duplicate_code)
            raise NuvlyError(
                f"Mongo duplicate key conflict in {collection_name}. Check logs for index details.",
                500,
                "MONGO_DUPLICATE_KEY",
            )
        if result.matched_count == 0:
            raise NuvlyError(not_found_message, 404, not_found_code)
        return self._public_document(document)

    def count_documents(self, collection_name: str, filters: Dict[str, Any]) -> int:
        return self.collection(collection_name).count_documents(filters)
